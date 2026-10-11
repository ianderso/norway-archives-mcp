"""Place names: Kartverket's register, and Digitalarkivet's historical municipalities.

Two different lists:

* **Kartverket's place-name register** (Sentralt stedsnavnregister, through
  ``api.kartverket.no/stedsnavn/v1``, no key) holds today's official names:
  farms, hamlets, mountains, lakes, with coordinates and today's municipality.
  Municipalities have merged since (Leikanger into Sogndal in 2020, for example),
  so a farm's municipality here is often not the one its church books sit
  under.
* **Digitalarkivet's municipality list** is the one its searches filter by:
  about 860 historical municipalities with four-digit numbers (1640 Røros,
  0301 Oslo), each under its old county. It ships with this package, read
  from the search form on 2026-10-11.
"""

from __future__ import annotations

import json
import unicodedata
from functools import cache
from importlib import resources
from typing import Any
from urllib.parse import urlencode

KARTVERKET = "https://api.kartverket.no/stedsnavn/v1/navn"


@cache
def codes() -> dict:
    """Digitalarkivet's municipality, county and list-type codes."""
    raw = resources.files("norway_archives_mcp").joinpath("data/digitalarkivet_codes.json")
    return json.loads(raw.read_text(encoding="utf-8"))


def _fold(text: str) -> str:
    """Compare names without case. Accents are kept: å, æ and ø are letters of their own."""
    return unicodedata.normalize("NFC", text.strip()).casefold()


def municipalities(query: str = "", county: str = "") -> list[dict]:
    """Historical municipalities whose name or number matches, optionally in one county."""
    data = codes()
    counties = data["counties"]
    want_county = _fold(county)
    out = []
    for number, entry in data["municipalities"].items():
        county_name = counties.get(entry["county"], "")
        if want_county and want_county not in (_fold(county_name), entry["county"]):
            continue
        if query and not (number == query.strip() or _fold(query) in _fold(entry["name"])):
            continue
        out.append({"number": number, "name": entry["name"], "county": county_name})
    return sorted(out, key=lambda m: (m["name"], m["number"]))


def resolve_municipality(value: str) -> tuple[str | None, list[dict]]:
    """One municipality number for a name or number, or the candidates if several match.

    A four-digit number is taken as is when known. A name matches exactly
    (ignoring case); "Kvam, Hordaland" picks one of several of that name.
    Returns ``(number, [])`` on a single match, ``(None, candidates)`` otherwise.
    """
    text = value.strip()
    data = codes()["municipalities"]
    if text.isdigit():
        return (text, []) if text in data else (None, [])
    name, _, county = text.partition(",")
    exact = [m for m in municipalities(county=county.strip()) if _fold(m["name"]) == _fold(name)]
    if len(exact) == 1:
        return exact[0]["number"], []
    if exact:
        return None, exact
    return None, municipalities(name)[:15]


def list_type_code(value: str) -> str | None:
    """A Digitalarkivet list-type code for a code or its English label."""
    types = codes()["list_types"]
    text = value.strip()
    if text.lower() in types:
        return text.lower()
    for code, label in types.items():
        if _fold(label) == _fold(text):
            return code
    return None


def list_types() -> dict[str, str]:
    """Digitalarkivet's list types: code → English label."""
    return dict(codes()["list_types"])


# --------------------------------------------------------------------------- #
# Kartverket
# --------------------------------------------------------------------------- #
def kartverket_url(name: str, *, municipality: str, county: str, fuzzy: bool, limit: int) -> str:
    """A search of today's official place names."""
    params = {"sok": name, "utkoordsys": "4258", "treffPerSide": str(limit), "side": "1"}
    if fuzzy:
        params["fuzzy"] = "true"
    if municipality:
        key = "knr" if municipality.isdigit() else "kommunenavn"
        params[key] = municipality
    if county:
        params["fnr" if county.isdigit() else "fylkesnavn"] = county
    return f"{KARTVERKET}?{urlencode(params)}"


def shape_place_names(data: Any) -> dict:
    """Kartverket's answer, trimmed."""
    meta = (data or {}).get("metadata") or {}
    out = []
    for entry in (data or {}).get("navn") or []:
        point = entry.get("representasjonspunkt") or {}
        out.append(
            {
                "name": entry.get("skrivemåte", ""),
                "object_type": entry.get("navneobjekttype", ""),
                "place_number": entry.get("stedsnummer"),
                "municipalities": [
                    f"{m.get('kommunenavn', '')} ({m.get('kommunenummer', '')})"
                    for m in entry.get("kommuner") or []
                ],
                "counties": [f.get("fylkesnavn", "") for f in entry.get("fylker") or []],
                "latitude": point.get("nord"),
                "longitude": point.get("øst"),
                "status": entry.get("stedstatus", ""),
                "map": (
                    f"https://norgeskart.no/#!?project=norgeskart&zoom=12"
                    f"&lat={point.get('nord')}&lon={point.get('øst')}"
                    if point
                    else ""
                ),
            }
        )
    return {"total": int(meta.get("totaltAntallTreff") or 0), "names": out}
