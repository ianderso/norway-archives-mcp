"""Nasjonalbiblioteket (the National Library of Norway): search, pages and OCR text.

The library's API (api.nb.no) is documented and needs no key. It searches the
catalogue and the full text of digitised books and newspapers, returns
snippets from inside a book, serves IIIF manifests and images, and ALTO OCR
for each page. What may be *shown* depends on where the request comes from:
material marked ``EVERYWHERE`` opens anywhere; ``NORWAY`` material (most books
from 1900 to 2005, through the Bokhylla agreement) opens only from Norwegian
addresses, though search still reports page numbers and short snippets; ``NB``
material is for the library's reading rooms. This module turns the API's
answers into plain data.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urlencode

API = "https://api.nb.no/catalog/v1"

#: Media types the catalogue filters by (``filter=mediatype:<value>``).
MEDIA_TYPES = {
    "books": "bøker",
    "newspapers": "aviser",
    "journals": "tidsskrift",
    "maps": "kart",
    "letters": "brev",
    "manuscripts": "manuskripter",
    "pictures": "bilder",
    "private archives": "privatarkivmateriale",
}

#: Where an item may be read, in the API's words and in plain ones.
ACCESS = {
    "EVERYWHERE": "everywhere",
    "NORWAY": "norway_only",
    "NB": "library_only",
    "LIBRARY": "library_only",
}


def search_url(
    query: str,
    *,
    media_type: str,
    full_text: bool,
    year_from: int | None,
    year_to: int | None,
    digital_only: bool,
    page: int,
    size: int,
) -> str:
    """A catalogue search."""
    params: list[tuple[str, str]] = [("q", query), ("size", str(size)), ("page", str(page))]
    if full_text:
        params.append(("searchType", "FULL_TEXT_SEARCH"))
    if media_type:
        params.append(("filter", f"mediatype:{media_type}"))
    if year_from or year_to:
        params.append(("filter", f"year:[{year_from or 1000} TO {year_to or 2999}]"))
    if digital_only:
        params.append(("digitalAccessibleOnly", "true"))
    return f"{API}/items?{urlencode(params)}"


def item_url(item_id: str) -> str:
    """One item's catalogue record."""
    return f"{API}/items/{quote(item_id)}"


def fragments_url(item_id: str, query: str, fragments: int) -> str:
    """Snippets matching ``query`` inside one item."""
    params = urlencode({"q": query, "fragSize": "200", "fragments": str(fragments)})
    return f"{API}/items/{quote(item_id)}/contentfragments?{params}"


def manifest_url(item_id: str) -> str:
    """One item's IIIF Presentation 2 manifest."""
    return f"{API}/iiif/{quote(item_id)}/manifest"


def alto_url(item_id: str, page_id: str) -> str:
    """The ALTO OCR file of one page."""
    return f"{API}/metadata/{quote(item_id)}/altos/{quote(page_id)}"


def reader_url(item_id: str) -> str:
    """The library's own reader for an item, for a person to open."""
    return f"https://www.nb.no/items/{item_id}"


def image_url(page_id: str, max_pixels: int | None) -> str:
    """An IIIF Image API 2 request for a whole page from the library's resolver."""
    size = "full" if not max_pixels else f"!{max_pixels},{max_pixels}"
    return f"https://www.nb.no/services/image/resolver/{quote(page_id)}/full/{size}/0/native.jpg"


def valid_item_id(item_id: str) -> bool:
    """A catalogue id is 32 hexadecimal characters."""
    return bool(re.fullmatch(r"[0-9a-f]{32}", item_id or ""))


def valid_page_id(page_id: str) -> bool:
    """A page id is a URN such as ``URN:NBN:no-nb_digibok_2009031803022_0061``."""
    return bool(re.fullmatch(r"URN:NBN:no-nb_[A-Za-z0-9_-]+", page_id or ""))


# --------------------------------------------------------------------------- #
# Shaping
# --------------------------------------------------------------------------- #
def access_of(item: dict) -> dict:
    """Where an item may be read, and whether it is public domain."""
    info = item.get("accessInfo") or {}
    allowed = str(info.get("accessAllowedFrom") or "")
    return {
        "readable_from": ACCESS.get(allowed, allowed.lower() or "unknown"),
        "public_domain": bool(info.get("isPublicDomain")),
        "digitised": bool(info.get("isDigital", True)),
        "viewable": str(info.get("viewability") or "").upper() == "ALL",
    }


def shape_item(item: dict) -> dict:
    """One catalogue hit, trimmed to what a researcher needs."""
    md = item.get("metadata") or {}
    origin = md.get("originInfo") or {}
    issued = str(origin.get("issued") or "")
    creators = md.get("creators") or []
    if creators and isinstance(creators[0], dict):
        creators = [c.get("name", "") for c in creators]
    if not creators:
        # A single item's record lists people with roles instead.
        creators = [
            p.get("name", "")
            for p in md.get("people") or []
            if isinstance(p, dict) and p.get("name")
        ]
    item_id = str(item.get("id", ""))
    return {
        "item_id": item_id,
        "title": str(md.get("title") or ""),
        "creators": [str(c) for c in creators][:6],
        "issued": issued[:4] if re.fullmatch(r"\d{8}", issued) else issued,
        "media_type": ", ".join(md.get("mediaTypes") or []),
        "subjects": (md.get("subjectName") or [])[:6],
        "places": ((md.get("subject") or {}).get("geographics") or [])[:6],
        **access_of(item),
        "url": reader_url(item_id),
    }


def shape_search(data: Any) -> dict:
    """A search answer: the total and the hits."""
    page = (data or {}).get("page") or {}
    items = ((data or {}).get("_embedded") or {}).get("items") or []
    return {
        "total": int(page.get("totalElements") or 0),
        "pages": int(page.get("totalPages") or 0),
        "items": [shape_item(i) for i in items],
    }


def shape_fragments(data: Any) -> list[dict]:
    """Snippets from inside an item, with the printed page and the page id."""
    out = []
    for frag in (data or {}).get("contentFragments") or []:
        text = re.sub(r"\s+", " ", str(frag.get("text") or "")).strip()
        out.append(
            {
                "page": str(frag.get("pageNumber") or ""),
                "page_id": str(frag.get("pageid") or ""),
                "snippet": text.replace("<em>", "**").replace("</em>", "**"),
            }
        )
    return out


def parse_manifest(data: Any) -> dict:
    """An item's pages from its IIIF 2 manifest: label, id, size and OCR address.

    Returns ``{"label", "metadata", "pages": [[page_id, label, width, height, alto], ...]}``.
    """
    if not isinstance(data, dict) or "sequences" not in data:
        raise ValueError("not a IIIF Presentation 2 manifest")
    metadata = {}
    for entry in data.get("metadata") or []:
        name = str(entry.get("label") or "")
        value = re.sub(r"<[^>]+>", " ", str(entry.get("value") or ""))
        if name:
            metadata[name] = re.sub(r"\s+", " ", value).strip()
    pages = []
    for canvas in (data.get("sequences") or [{}])[0].get("canvases") or []:
        cid = str(canvas.get("@id") or "")
        page_id = cid.rsplit("/", 1)[-1]
        see = canvas.get("@seeAlso") or {}
        alto = see.get("@id", "") if isinstance(see, dict) else ""
        pages.append(
            [
                page_id,
                str(canvas.get("label") or ""),
                int(canvas.get("width") or 0),
                int(canvas.get("height") or 0),
                alto,
            ]
        )
    return {"label": str(data.get("label") or ""), "metadata": metadata, "pages": pages}


def alto_text(xml: str) -> str:
    """The plain text of an ALTO page: lines in reading order, words joined by spaces.

    Hyphenated line ends (``HYP``) are kept as written, so the text matches
    the page a reader will check it against.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"unreadable ALTO: {exc}") from None
    lines = []
    for line in root.iter():
        if not line.tag.endswith("TextLine"):
            continue
        words = []
        for child in line:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "String":
                words.append(child.get("CONTENT", ""))
            elif tag == "HYP":
                words.append(child.get("CONTENT", "-"))
        if words:
            lines.append(" ".join(w for w in words if w).replace(" -", "-"))
    return "\n".join(lines)
