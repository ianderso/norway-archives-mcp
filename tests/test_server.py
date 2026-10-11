"""The tools as a client calls them, over recorded answers."""

from __future__ import annotations

import httpx
import pytest
import respx

from .conftest import (
    FT,
    GOTO,
    JPEG,
    KARTVERKET,
    KB,
    KB_UUID,
    NB_API,
    NB_IMAGES,
    NB_ITEM,
    NB_PAGE51,
    SITE,
    SOURCE,
    URN,
    VIEWER,
    call_tool,
    fixture,
    html,
    redirect,
)

MANIFEST = f"{VIEWER}/api/media-file/image/presentation/manifest/{SOURCE}.json"


def _route_source(router: respx.MockRouter) -> None:
    router.get(f"{SITE}/en/source/{SOURCE}").mock(return_value=html("da_source_6540.html"))
    router.get(MANIFEST).mock(
        return_value=httpx.Response(200, json=fixture("da_manifest_6540.json"))
    )


# --------------------------------------------------------------------------- #
# Digitalarkivet
# --------------------------------------------------------------------------- #
@respx.mock
async def test_person_search_resolves_the_municipality_and_list_type(served):
    route = respx.get(url__startswith=f"{SITE}/en/search/persons/advanced").mock(
        return_value=html("da_persons_roros.html")
    )
    result = await call_tool(
        "da_search_persons",
        last_name="Rønning",
        municipality="Røros",
        list_type="Born and baptised",
    )
    assert result["total"] == 4
    assert result["searched"] == {
        "municipality": "Røros (1640)",
        "list_type": "Born and baptised (dp)",
    }
    sent = str(route.calls.last.request.url)
    assert "m%5B%5D=1640" in sent and "lt%5B%5D=dp" in sent


async def test_person_search_needs_a_name(served):
    assert (await call_tool("da_search_persons", municipality="Røros"))["error"] == "no_name"


async def test_an_ambiguous_municipality_lists_the_candidates(served):
    result = await call_tool("da_search_persons", last_name="Aas", municipality="Kvam")
    assert result["error"] == "ambiguous_municipality" and len(result["candidates"]) >= 2


async def test_an_unknown_list_type_lists_the_codes(served):
    result = await call_tool("da_search_persons", last_name="Aas", list_type="baptisms please")
    assert result["error"] == "unknown_list_type" and "kf" in result["list_types"]


@respx.mock
async def test_a_record_comes_with_its_scan_and_a_citation(served):
    respx.get(f"{SITE}/en/view/255/pd00000024592808").mock(
        return_value=html("da_record_roros_baptism.html")
    )
    result = await call_tool("da_get_record", record="view/255/pd00000024592808")
    assert result["scanned_pages"] == [KB]
    assert "pd00000024592808" in result["citation"]["text"]
    assert "transcription is a lead" in result["note"]


async def test_a_record_must_be_a_digitalarkivet_address(served):
    assert (await call_tool("da_get_record", record="https://example.org/x"))[
        "error"
    ] == "bad_record"


@respx.mock
async def test_source_search_needs_a_query_or_a_place(served):
    assert (await call_tool("da_search_sources", list_type="kf"))["error"] == "too_broad"
    respx.get(url__startswith=f"{SITE}/en/search/sources").mock(
        return_value=html("da_sources_roros_kf.html")
    )
    result = await call_tool("da_search_sources", municipality="1640", list_type="kf")
    assert result["total"] == 2


@respx.mock
async def test_a_source_maps_its_lists_to_image_numbers(served):
    _route_source(respx)
    result = await call_tool("da_get_source", source_id=SOURCE)
    assert result["image_count"] == 464
    starts = [s["first_image"] for s in result["sections"]]
    assert starts == sorted(starts)
    confirmations = next(s for s in result["sections"] if s["list_type"] == "kf")
    assert confirmations["first_image"] < confirmations["likely_last_image"]


@respx.mock
async def test_a_source_without_new_viewer_scans_says_where_to_look(served):
    respx.get(f"{SITE}/en/source/{SOURCE}").mock(return_value=html("da_source_6540.html"))
    respx.get(MANIFEST).mock(return_value=httpx.Response(404, text="not found"))
    result = await call_tool("da_get_source", source_id=SOURCE)
    assert result["scans"] is None and "ft…" in result["note"]


@respx.mock
async def test_list_pages_can_start_at_a_section(served):
    _route_source(respx)
    result = await call_tool("da_list_pages", source_id=SOURCE, section="kf", count=2)
    assert len(result["pages"]) == 2
    first = result["pages"][0]
    assert first["page_id"].startswith("kb") and first["permalink"].startswith(GOTO)
    assert result["next_start"] == first["image"] + 2


@respx.mock
async def test_list_pages_names_the_lists_when_a_section_is_missing(served):
    _route_source(respx)
    result = await call_tool("da_list_pages", source_id=SOURCE, section="sj")
    assert result["error"] == "no_such_section" and "kf" in result["message"]


@respx.mock
async def test_download_by_kb_resolves_the_permalink_and_cites_the_page(served, download_dir):
    respx.get(f"{GOTO}/{KB}").mock(
        return_value=redirect(f"{VIEWER}/source/{SOURCE}/parish/{KB_UUID}")
    )
    respx.get(MANIFEST).mock(
        return_value=httpx.Response(200, json=fixture("da_manifest_6540.json"))
    )
    image = respx.get(url__startswith=f"{VIEWER}/api/media-file/image/{KB_UUID}/full/").mock(
        return_value=httpx.Response(200, content=JPEG)
    )
    target = download_dir / "page.jpg"
    result = await call_tool(
        "da_download_page", destination=str(target), page_id=KB, max_pixels=1500
    )
    assert result["image"] == 151 and result["source_id"] == SOURCE
    assert "!1500,1500" in str(image.calls.last.request.url)
    citation = result["citation"]
    assert citation["archive_reference"] == "AV/SAT-A-1456/681/L0932"
    assert citation["permalink"] == f"{GOTO}/{KB}" and "image 151 of 464" in citation["text"]
    assert target.read_bytes() == JPEG


@respx.mock
async def test_download_of_a_census_page_uses_the_urn(served, download_dir):
    respx.get(f"{SITE}/en/{FT}").mock(
        return_value=redirect("https://media.digitalarkivet.no/view/38322/19", 302)
    )
    respx.get(f"{SITE}/en/source/38322").mock(return_value=html("da_source_6540.html"))
    respx.get(f"{URN}/URN:NBN:no-a1450-{FT}.jpg").mock(
        return_value=httpx.Response(200, content=JPEG)
    )
    result = await call_tool(
        "da_download_page", destination=str(download_dir / "c.jpg"), page_id=FT
    )
    assert (result["source_id"], result["image"]) == (38322, 19)
    assert result["citation"]["image_url"].endswith(f"{FT}.jpg")


@respx.mock
async def test_a_restricted_page_is_not_downloaded(served, download_dir):
    manifest = fixture("da_manifest_6540.json")
    manifest["items"][0]["items"][0]["items"][0]["isRestricted"] = True
    respx.get(MANIFEST).mock(return_value=httpx.Response(200, json=manifest))
    result = await call_tool(
        "da_download_page", destination=str(download_dir / "r.jpg"), source_id=SOURCE, image=1
    )
    assert result["error"] == "restricted" and not (download_dir / "r.jpg").exists()


async def test_download_needs_a_page(served, download_dir):
    result = await call_tool("da_download_page", destination=str(download_dir / "n.jpg"))
    assert result["error"] == "no_page"
    result = await call_tool(
        "da_download_page", destination=str(download_dir / "n.jpg"), page_id="../etc"
    )
    assert result["error"] == "bad_page_id"


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("relative.jpg", "relative_destination"),
        ("/{dir}/page.png", "bad_extension"),
        ("/{dir}/.hidden/page.jpg", "hidden_path"),
        ("/{dir}/missing/page.jpg", "no_such_directory"),
    ],
)
async def test_destination_rules(served, download_dir, name, error):
    destination = name.replace("/{dir}", str(download_dir))
    result = await call_tool("da_download_page", destination=destination, page_id=KB)
    assert result["error"] == error


async def test_nothing_is_written_outside_the_download_folder(served, download_dir, tmp_path):
    result = await call_tool("da_download_page", destination=str(tmp_path / "x.jpg"), page_id=KB)
    assert result["error"] == "outside_download_dir"


async def test_an_existing_file_is_never_overwritten(served, download_dir):
    existing = download_dir / "there.jpg"
    existing.write_bytes(b"keep")
    result = await call_tool("da_download_page", destination=str(existing), page_id=KB)
    assert result["error"] == "destination_exists" and existing.read_bytes() == b"keep"


# --------------------------------------------------------------------------- #
# National Library
# --------------------------------------------------------------------------- #
@respx.mock
async def test_library_search_translates_the_media_type_and_years(served):
    route = respx.get(url__startswith=f"{NB_API}/catalog/v1/items").mock(
        return_value=httpx.Response(200, json=fixture("nb_search_years.json"))
    )
    result = await call_tool("nb_search", query="Røros kobberverk", year_from=1800, year_to=1900)
    assert result["items"]
    sent = str(route.calls.last.request.url)
    assert "mediatype%3Ab%C3%B8ker" in sent and "year%3A%5B1800+TO+1900%5D" in sent


async def test_an_unknown_media_type_is_refused(served):
    assert (await call_tool("nb_search", query="x", media_type="films"))[
        "error"
    ] == "unknown_media_type"


@respx.mock
async def test_search_inside_gives_pages_and_access(served):
    respx.get(f"{NB_API}/catalog/v1/items/{NB_ITEM}").mock(
        return_value=httpx.Response(200, json=fixture("nb_item_open.json"))
    )
    respx.get(url__startswith=f"{NB_API}/catalog/v1/items/{NB_ITEM}/contentfragments").mock(
        return_value=httpx.Response(200, json=fixture("nb_fragments.json"))
    )
    result = await call_tool("nb_search_inside", item_id=NB_ITEM, query="Hiort", max_snippets=5)
    assert result["hits"][0]["page"] == "51"
    assert result["item"]["readable_from"] == "everywhere"


async def test_search_inside_checks_the_item_id(served):
    assert (await call_tool("nb_search_inside", item_id="x", query="y"))["error"] == "bad_item_id"


def _route_nb_page(router: respx.MockRouter) -> None:
    router.get(f"{NB_API}/catalog/v1/items/{NB_ITEM}").mock(
        return_value=httpx.Response(200, json=fixture("nb_item_open.json"))
    )
    router.get(f"{NB_API}/catalog/v1/iiif/{NB_ITEM}/manifest").mock(
        return_value=httpx.Response(200, json=fixture("nb_manifest_open_first80.json"))
    )


@respx.mock
async def test_a_library_page_by_printed_number_carries_its_text(served):
    _route_nb_page(respx)
    respx.get(f"{NB_API}/catalog/v1/metadata/{NB_ITEM}/altos/{NB_PAGE51}").mock(
        return_value=httpx.Response(200, text=fixture("nb_alto_page51.xml"))
    )
    result = await call_tool("nb_get_page", item_id=NB_ITEM, page="51")
    assert result["page_id"] == NB_PAGE51 and result["text"].startswith("1670")
    assert "p. 51" in result["citation"]["text"]


@respx.mock
async def test_a_library_page_downloads(served, download_dir):
    _route_nb_page(respx)
    respx.get(url__startswith=f"{NB_IMAGES}/services/image/resolver/").mock(
        return_value=httpx.Response(200, content=JPEG)
    )
    result = await call_tool(
        "nb_download_page", destination=str(download_dir / "p51.jpg"), item_id=NB_ITEM, page="51"
    )
    assert result["page"] == "51" and (download_dir / "p51.jpg").exists()


@respx.mock
async def test_a_missing_library_page_says_how_to_ask(served):
    _route_nb_page(respx)
    result = await call_tool("nb_get_page", item_id=NB_ITEM, page="9999")
    assert result["error"] == "no_such_page"


@respx.mock
async def test_a_refusal_from_norway_only_material_is_explained(served, download_dir):
    _route_nb_page(respx)
    respx.get(url__startswith=f"{NB_IMAGES}/services/image/resolver/").mock(
        return_value=httpx.Response(403)
    )
    result = await call_tool(
        "nb_download_page", destination=str(download_dir / "x.jpg"), item_id=NB_ITEM, page="51"
    )
    assert result["error"] == "not_open_here"


# --------------------------------------------------------------------------- #
# Places, local tools, contract
# --------------------------------------------------------------------------- #
@respx.mock
async def test_place_names(served):
    respx.get(url__startswith=f"{KARTVERKET}/stedsnavn/v1/navn").mock(
        return_value=httpx.Response(200, json=fixture("kv_roros.json"))
    )
    result = await call_tool("place_names", name="Røros", limit=5)
    assert result["names"][0]["name"] == "Røros"


async def test_municipalities_is_local(served):
    result = await call_tool("municipalities", query="Røros")
    assert result["municipalities"][0]["number"] == "1640"


async def test_cache_status_reports_the_budget(served):
    result = await call_tool("cache_status")
    assert result["digitalarkivet_budget"]["limit"] == 600


async def test_an_unknown_parameter_is_refused_not_ignored(served):
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError):
        await call_tool("municipalities", qeury="Røros")


@respx.mock
async def test_a_spent_budget_is_reported_with_cached_answers_still_working(served, monkeypatch):
    monkeypatch.setattr(served, "_budget", 0)
    result = await call_tool("da_get_source", source_id=SOURCE)
    assert result["error"] == "budget_spent"
