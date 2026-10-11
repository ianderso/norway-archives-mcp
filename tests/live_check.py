"""Ask the live services what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check

Every tool is called once against the same neutral examples the fixtures use
(Røros, its 1860-1878 church book, its 1865 census, an 1894 history of the
copper works), and each answer is checked for the shape the parsers expect.
The client paces itself: about a dozen Digitalarkivet requests, five seconds
apart, so the run takes a little over a minute and spends a dozen requests of
the day's budget.

It is not a test module: pytest does not collect it, and CI never runs it,
because the suite must never depend on someone else's server being up. Three
images are downloaded to a temporary directory, set as the download folder,
and deleted with it. The cache goes to a temporary directory too, so every
call is live.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from norway_archives_mcp import server
from norway_archives_mcp.client import NorHttp
from norway_archives_mcp.config import Config

#: (tool, arguments, check, what the check means). ``{tmp}`` in an argument
#: is replaced by the temporary directory.
CHECKS: list[tuple[str, dict, Callable[[dict], bool], str]] = [
    (
        "da_search_sources",
        {"municipality": "Røros", "list_type": "kf", "year_from": 1860, "year_to": 1880},
        lambda r: any(s["source_id"] == 6540 for s in r["sources"]),
        "the source search finds the Røros 1860-1878 church book among confirmation sources",
    ),
    (
        "da_get_source",
        {"source_id": 6540},
        lambda r: (
            r["archive_reference"] == "AV/SAT-A-1456/681/L0932"
            and r["image_count"] == 464
            and any(s["list_type"] == "kf" and s["first_image"] for s in r["sections"])
        ),
        "the source page and manifest still give the reference, 464 images and list starts",
    ),
    (
        "da_list_pages",
        {"source_id": 6540, "section": "kf", "count": 2},
        lambda r: r["pages"][0]["page_id"].startswith("kb"),
        "a section's pages list with permanent ids",
    ),
    (
        "da_search_persons",
        {
            "last_name": "Rønning",
            "municipality": "1640",
            "event_year_from": 1865,
            "event_year_to": 1880,
        },
        lambda r: r["total"] >= 4 and any("pd00000024592808" in h["record_url"] for h in r["hits"]),
        "the person search still finds the 1875 baptism and the 1865 census",
    ),
    (
        "da_get_record",
        {"record": "view/255/pd00000024592808"},
        lambda r: r["scanned_pages"] == ["kb20070419660152"] and r["source_id"] == 6540,
        "a church-book record still links its scanned page",
    ),
    (
        "da_get_record",
        {"record": "census/person/pf01038322000172"},
        lambda r: r["scanned_pages"] == ["ft20090803410602"],
        "a census record still links its ft page",
    ),
    (
        "da_download_page",
        {"destination": "{tmp}/kb.jpg", "page_id": "kb20070419660152", "max_pixels": 800},
        lambda r: r["image"] == 151 and r["bytes"] > 10_000,
        "a kb permalink still resolves through goto and the IIIF image service",
    ),
    (
        "da_download_page",
        {"destination": "{tmp}/ft.jpg", "page_id": "ft20090803410602"},
        lambda r: (r["source_id"], r["image"]) == (38322, 19) and r["bytes"] > 100_000,
        "an ft page still resolves through the old viewer and the URN resolver",
    ),
    (
        "nb_search",
        {"query": "Røros kobberverk", "year_from": 1800, "year_to": 1920, "digitised_only": True},
        lambda r: r["total"] > 0 and any(i["readable_from"] == "everywhere" for i in r["items"]),
        "the library's search still answers with access information",
    ),
    (
        "nb_search_inside",
        {"item_id": "6c40d98813a942688b706a97e15dde22", "query": "Hiort", "max_snippets": 3},
        lambda r: r["hits"] and r["hits"][0]["page"] == "51",
        "search inside still gives the printed page",
    ),
    (
        "nb_get_page",
        {"item_id": "6c40d98813a942688b706a97e15dde22", "page": "51"},
        lambda r: r.get("text", "").startswith("1670"),
        "an open page still gives ALTO text",
    ),
    (
        "nb_download_page",
        {
            "destination": "{tmp}/nb.jpg",
            "item_id": "6c40d98813a942688b706a97e15dde22",
            "page": "51",
            "max_pixels": 800,
        },
        lambda r: r["bytes"] > 10_000,
        "an open page image still downloads",
    ),
    (
        "nb_search_inside",
        {"item_id": "73132b1f152438b650d33aa55c5152f9", "query": "Røros", "max_snippets": 2},
        lambda r: r["item"]["readable_from"] == "norway_only",
        "a Norway-only item still answers search-inside from abroad, marked as such",
    ),
    (
        "place_names",
        {"name": "Røros", "limit": 3},
        lambda r: r["names"] and r["names"][0]["latitude"],
        "Kartverket still returns names with coordinates",
    ),
]


async def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "images").mkdir()
        server.runtime.config = Config(cache_dir=root / "cache", download_dir=root / "images")
        server.runtime.http = NorHttp(root / "cache")
        for tool, args, check, meaning in CHECKS:
            arguments = {
                k: v.replace("{tmp}", str(root / "images")) if isinstance(v, str) else v
                for k, v in args.items()
            }
            result = await server.mcp.call_tool(tool, arguments)
            data = json.loads(result.content[0].text)
            try:
                ok = "error" not in data and bool(check(data))
            except (KeyError, IndexError, TypeError):
                ok = False
            failures += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {tool}: {meaning}")
            if not ok:
                print("     ", json.dumps(data, ensure_ascii=False)[:400])
        status = await server.mcp.call_tool("cache_status", {})
        budget = json.loads(status.content[0].text)["calls_by_service"]
        print(f"live calls by service: {budget}")
    print(f"{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
