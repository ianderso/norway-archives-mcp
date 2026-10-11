"""Digitalarkivet: addresses, page parsers and the IIIF manifest.

Digitalarkivet (www.digitalarkivet.no, run by Nasjonalarkivet, the National
Archives of Norway) publishes no API. Its search and record pages are plain
server-rendered HTML, and its new viewer (nye.digitalarkivet.no) serves a
standard IIIF Presentation 3 manifest for every scanned source. These parsers
read the English pages (``/en/``), whose labels are stable and documented in
docs/API-NOTES.md with the date they were recorded.

Everything here is pure: text in, plain data out. The tools in
:mod:`norway_archives_mcp.server` do the fetching and caching.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlencode, urlsplit

from bs4 import BeautifulSoup, Tag

SITE = "https://www.digitalarkivet.no"
VIEWER = "https://nye.digitalarkivet.no"
GOTO = "https://goto.digitalarkivet.no"
URN = "https://urn.digitalarkivet.no"

#: A permanent page id from a scan's file name: ``kb…`` for church books and
#: most other sources scanned since 2006, ``ft…`` for the transcribed censuses.
PAGE_ID_RE = re.compile(r"\b((?:kb|ft)\d{8,})\b")

#: A record address: ``/en/view/<db>/<id>`` or ``/en/census/person/<id>``.
RECORD_RE = re.compile(
    r"(?:https://www\.digitalarkivet\.no)?/?(?:[a-z]{2}/)?"
    r"(?P<path>view/\d+/[a-z]{2}\d+|census/person/[a-z]{2}\d+)"
)


class PageChanged(ValueError):
    """The page did not have the structure these parsers were written for."""


# --------------------------------------------------------------------------- #
# Addresses
# --------------------------------------------------------------------------- #
def persons_url(params: dict[str, Any]) -> str:
    """The advanced person search, with list parameters repeated as ``k[]=v``."""
    return f"{SITE}/en/search/persons/advanced?{_query(params)}"


def sources_url(params: dict[str, Any]) -> str:
    """The source search."""
    return f"{SITE}/en/search/sources?{_query(params)}"


def source_url(source_id: int) -> str:
    """A source's description page."""
    return f"{SITE}/en/source/{source_id}"


def manifest_url(source_id: int) -> str:
    """A source's IIIF Presentation 3 manifest in the new viewer."""
    return f"{VIEWER}/api/media-file/image/presentation/manifest/{source_id}.json"


def goto_url(kb: str) -> str:
    """The permanent address of one scanned page."""
    return f"{GOTO}/{kb}"


def urn_image_url(page_id: str) -> str:
    """The URN address of one scanned page's full-size JPEG: stable, and citable."""
    return f"{URN}/URN:NBN:no-a1450-{page_id}.jpg"


def old_permalink_url(page_id: str) -> str:
    """The classic site's address for a page id; it redirects to the old viewer."""
    return f"{SITE}/en/{page_id}"


def viewer_page_url(source_id: int, uuid: str) -> str:
    """One page in the new viewer."""
    return f"{VIEWER}/source/{source_id}/parish/{uuid}"


def record_url(ref: str) -> str | None:
    """A record's English address from an address or a ``view/…``/``census/…`` path."""
    m = RECORD_RE.search(ref.strip())
    return f"{SITE}/en/{m.group('path')}" if m else None


def image_url(service: str, max_pixels: int | None) -> str:
    """An IIIF Image API 3 request for the whole page, at most ``max_pixels`` on the long side."""
    size = "max" if not max_pixels else f"!{max_pixels},{max_pixels}"
    return f"{service.rstrip('/')}/full/{size}/0/default.jpg"


def _query(params: dict[str, Any]) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if value in (None, "", [], ()):
            continue
        if isinstance(value, list | tuple):
            pairs.extend((f"{key}[]", str(v)) for v in value)
        else:
            pairs.append((key, str(value)))
    return urlencode(pairs)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _soup(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, "html.parser")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _value(text: str) -> str:
    """A field value, with Digitalarkivet's ``-`` for "not recorded" made empty."""
    text = _clean(text)
    return "" if text in ("-", "&nbsp;") else text


def _pairs(node: Tag) -> list[tuple[str, str]]:
    """Label/value pairs: a value cell (``ssp-semibold``) and the label cell before it."""
    out = []
    for cell in node.select(".ssp-semibold"):
        label = cell.find_previous_sibling()
        if label is None:
            continue
        name = _clean(label.get_text(" ")).rstrip(":").strip()
        if name:
            out.append((name, _value(cell.get_text(" "))))
    return out


def _hits(soup: BeautifulSoup) -> int:
    node = soup.select_one("[data-hits]")
    if node is None:
        return 0
    try:
        return int(node["data-hits"])
    except (TypeError, ValueError):
        return 0


def _last_page(soup: BeautifulSoup) -> int:
    pages = [
        int(m.group(1))
        for a in soup.select(".pagination a[href]")
        if (m := re.search(r"[?&]page=(\d+)", a["href"]))
    ]
    current = soup.select_one(".pagination .active")
    if current and _clean(current.get_text()).isdigit():
        pages.append(int(_clean(current.get_text())))
    return max(pages, default=1)


def _source_id(href: str) -> int | None:
    m = re.search(r"/source/(\d+)", href or "")
    return int(m.group(1)) if m else None


def _field(unit: Tag, cls: str) -> str:
    node = unit.select_one(f".{cls}")
    if node is None:
        return ""
    label = node.find("span")
    text = node.get_text(" ")
    if label is not None:
        text = text.replace(label.get_text(" "), "", 1)
    return _value(text)


def no_results_page(text: str) -> bool:
    """True if a search page rendered but its result list is missing entirely."""
    return 'id="searchResultList"' not in text and "data-hits" not in text


# --------------------------------------------------------------------------- #
# Person search
# --------------------------------------------------------------------------- #
def parse_persons(text: str) -> dict:
    """The hits on one page of the advanced person search."""
    soup = _soup(text)
    listing = soup.select_one("#searchResultList")
    total = _hits(soup)
    if listing is None:
        if total == 0 and soup.select_one(".search-result-container") is not None:
            return {"total": 0, "pages": 0, "hits": []}
        if no_results_page(text):
            return {"total": 0, "pages": 0, "hits": []}
        raise PageChanged("no result list on the person-search page")
    hits = []
    for unit in listing.select("div.unit"):
        link = unit.select_one(".name a[href]")
        if link is None:
            continue
        born = link.select_one(".born")
        born_text = _clean(born.get_text(" ")) if born else ""
        if born is not None:
            born.extract()
        source = unit.select_one(".source a[href]")
        gender = unit.select_one(".gender .sr-only")
        hits.append(
            {
                "name": _clean(link.get_text(" ")),
                "born": born_text.strip("() ").removeprefix("b.").strip(),
                "gender": _clean(gender.get_text()).strip("() ") if gender else "",
                "domicile": _field(unit, "place"),
                "event_date": _field(unit, "action"),
                "position": _field(unit, "stilling-stand"),
                "role": _field(unit, "role"),
                "record_url": link["href"],
                "source_id": _source_id(source["href"]) if source else None,
                "source": _clean(source.get_text(" ")) if source else "",
            }
        )
    return {"total": total, "pages": _last_page(soup) if hits else 0, "hits": hits}


# --------------------------------------------------------------------------- #
# A record (church-book entry, census person, emigrant)
# --------------------------------------------------------------------------- #
def parse_record(text: str, url: str) -> dict:
    """A transcribed record: its fields, the people in it, its source and its scan."""
    soup = _soup(text)
    perm = soup.select_one("#permanentId")
    if perm is None:
        raise PageChanged("no permanent id on the record page")
    scans = sorted({m.group(1) for m in PAGE_ID_RE.finditer(text)})
    breadcrumb = [_clean(li.get_text(" ")) for li in soup.select("ul.da-breadcrumb li")]
    source_link = soup.select_one('ul.da-breadcrumb a[href*="/en/source/"]') or soup.select_one(
        'a[href*="/en/source/"]'
    )
    sections: list[dict] = []
    for panel in soup.select("div.panel"):
        heading = panel.select_one(".panel-heading, .panel-title")
        title = _clean(heading.get_text(" ")).rstrip(":") if heading else ""
        items = panel.select(".data-item")
        if items:
            people = []
            for item in items:
                head = item.select_one("h4")
                link = head.select_one("a[href]") if head else None
                people.append(
                    {
                        "heading": _clean(head.get_text(" ")) if head else "",
                        "url": link["href"] if link else "",
                        "current": "current" in (item.get("class") or []),
                        "fields": dict(_pairs(item)),
                    }
                )
            sections.append({"section": title, "people": people})
        else:
            fields = {k: v for k, v in _pairs(panel) if v}
            sections.append({"section": title, "fields": fields})
        panel.extract()
    cards: dict[str, dict[str, str]] = {}
    for card in soup.select("div.card"):
        heading = card.select_one(".heading")
        title = _clean(heading.get_text(" ")).rstrip(":") if heading else ""
        fields: dict[str, str] = {}
        for name, value in _pairs(card):
            fields.setdefault(name, value)
        cards[title or f"card {len(cards) + 1}"] = fields
        card.extract()
    fields: dict[str, str] = {}
    source_info: dict[str, str] = {}
    target = fields
    for name, value in _pairs(soup):
        if name == "Source information":
            target = source_info
        target.setdefault(name, value)
    if source_info:
        cards = {"Source information": source_info, **cards}
    return {
        "record_url": url,
        "permanent_id": _clean(perm.get_text()),
        "title": breadcrumb[-1] if breadcrumb else "",
        "breadcrumb": breadcrumb[1:],
        "fields": {k: v for k, v in fields.items() if v},
        "sections": sections,
        "about_the_source": cards,
        "source_id": _source_id(source_link["href"]) if source_link else None,
        "source": _clean(source_link.get_text(" ")) if source_link else "",
        "scanned_pages": scans,
    }


# --------------------------------------------------------------------------- #
# Source search
# --------------------------------------------------------------------------- #
def parse_sources(text: str) -> dict:
    """The sources on one page of the source search."""
    soup = _soup(text)
    listing = soup.select_one("#searchResultList")
    total = _hits(soup)
    if listing is None:
        if total == 0:
            return {"total": 0, "pages": 0, "sources": []}
        raise PageChanged("no result list on the source-search page")
    out = []
    for unit in listing.select("div.unit"):
        link = unit.select_one(".name a[href]")
        if link is None:
            continue
        lists = []
        for item in unit.select(".lists .unit-list"):
            label = item.select_one("strong")
            name = _clean(label.get_text(" ")).rstrip(":") if label else ""
            span = item.select_one("span")
            years = (
                _clean(span.get_text(" ")).replace(_clean(label.get_text(" ")), "", 1).strip()
                if span and label
                else ""
            )
            browse = item.select_one('.scanned a[href*="current_list_type="]')
            code = re.search(r"current_list_type=([a-z]+)", browse["href"]) if browse else None
            search = item.select_one('.transcribed a[href*="/search/"]')
            lists.append(
                {
                    "list_type": code.group(1) if code else "",
                    "label": name,
                    "years": years,
                    "scanned": browse is not None,
                    "searchable": search is not None,
                }
            )
        scanned = unit.find("div", class_="scanned", recursive=False)
        transcribed = unit.find("div", class_="transcribed", recursive=False)
        searchable_text = _clean(transcribed.get_text(" ")) if transcribed else ""
        out.append(
            {
                "source_id": _source_id(link["href"]),
                "title": _clean(link.get_text(" ")),
                "archive": _field(unit, "archive"),
                "scanned": bool(scanned and scanned.select_one("a[href]"))
                or any(x["scanned"] for x in lists),
                "searchable": any(x["searchable"] for x in lists)
                or (bool(searchable_text) and searchable_text.lower() != "not searchable"),
                "lists": lists,
            }
        )
    return {"total": total, "pages": _last_page(soup) if out else 0, "sources": out}


# --------------------------------------------------------------------------- #
# One source
# --------------------------------------------------------------------------- #
def parse_source(text: str, source_id: int) -> dict:
    """A source's description and the first page of each list in its scans."""
    soup = _soup(text)
    pairs = _pairs_loose(soup)
    reference = pairs.get("Archive reference", "")
    if not reference and "Source ID" not in pairs:
        raise PageChanged("no archive reference or source id on the source page")
    crumbs = soup.select("ul.da-breadcrumb li")
    title_node = crumbs[-1] if crumbs else soup.select_one("h1")
    sections = []
    first_page = ""
    for link in soup.select(f'a[href*="/source/{source_id}/parish/"]'):
        href = html.unescape(link["href"])
        m = re.search(r"/parish/([0-9a-f-]{36})(?:\?(.*))?$", href)
        if not m:
            continue
        uuid, query = m.group(1), m.group(2) or ""
        label = _clean(link.get_text(" "))
        lt = re.search(r"current_list_type=([a-z]+)", query)
        if lt:
            sections.append({"list_type": lt.group(1), "label": label, "uuid": uuid})
        elif "view=index" not in query and not first_page:
            first_page = uuid
    return {
        "source_id": source_id,
        "title": _clean(title_node.get_text(" ")) if title_node else "",
        "archive_reference": reference,
        "fields": pairs,
        "sections": sections,
        "first_page_uuid": first_page,
    }


def _pairs_loose(soup: BeautifulSoup) -> dict[str, str]:
    """Label/value pairs on the source page, whose markup varies by block.

    Each label is a cell ending in ``:``; its value is the next cell. The
    first occurrence of a label wins.
    """
    out: dict[str, str] = {}
    for name, value in _pairs(soup):
        out.setdefault(name, value)
    for label in soup.find_all(string=re.compile(r":\s*$")):
        parent = label.parent
        if parent is None or parent.name in ("script", "style", "a"):
            continue
        name = _clean(label).rstrip(":").strip()
        if not name or len(name) > 60 or name in out:
            continue
        nxt = parent.find_next_sibling()
        if nxt is not None:
            value = _value(nxt.get_text(" "))
            if value and len(value) < 400:
                out[name] = value
    return out


# --------------------------------------------------------------------------- #
# IIIF manifest
# --------------------------------------------------------------------------- #
def parse_manifest(data: Any) -> dict:
    """The pages of a source's IIIF manifest, in order, with their permanent ids.

    Returns a compact form for caching: book label, metadata (label → text),
    and one ``[uuid, kb, width, height, restricted, service]`` row per page.
    """
    if not isinstance(data, dict) or data.get("type") != "Manifest":
        raise PageChanged("not a IIIF Presentation 3 manifest")
    metadata = {}
    for entry in data.get("metadata") or []:
        name = _lang(entry.get("label"))
        if name:
            metadata[name] = _clean(re.sub(r"<[^>]+>", " ", _lang(entry.get("value"))))
    pages = []
    for canvas in data.get("items") or []:
        uuid = str(canvas.get("id", "")).rsplit("/", 1)[-1].removesuffix(".json")
        annotation = ((canvas.get("items") or [{}])[0].get("items") or [{}])[0]
        kb = ""
        for entry in annotation.get("metadata") or []:
            if _lang(entry.get("label"), prefer="en") == "Filename":
                kb = _lang(entry.get("value")).split(".")[0]
        body = annotation.get("body") or {}
        service = ((body.get("service") or [{}])[0]).get("id", "")
        pages.append(
            [
                uuid,
                kb,
                int(canvas.get("width") or 0),
                int(canvas.get("height") or 0),
                bool(annotation.get("isRestricted")),
                service,
            ]
        )
    return {"label": _lang(data.get("label"), prefer="en"), "metadata": metadata, "pages": pages}


def _lang(value: Any, prefer: str = "en") -> str:
    """The text of a IIIF language map, preferring one language."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict) or not value:
        return ""
    for lang in (prefer, "en", "no", "nb", "nn", "none"):
        if value.get(lang):
            return " ".join(str(v) for v in value[lang])
    first = next(iter(value.values()))
    return " ".join(str(v) for v in first) if isinstance(first, list) else str(first)


def parse_old_viewer_location(location: str) -> tuple[int, int] | None:
    """The source id and image number in an old-viewer address (``/view/<source>/<image>``)."""
    m = re.match(r"^/view/(\d+)/(\d+)", urlsplit(location).path)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_viewer_location(location: str) -> tuple[int, str] | None:
    """The source id and page uuid in a viewer address a ``goto`` permalink points to."""
    parts = urlsplit(location)
    m = re.match(r"^/source/(\d+)/parish/([0-9a-f-]{36})", parts.path)
    return (int(m.group(1)), m.group(2)) if m else None
