"""Shared fixtures. Every test runs against mocked services; nothing touches the network.

The fixtures under ``fixtures/`` are real responses recorded on 2026-10-11
from Digitalarkivet, the National Library's API and Kartverket's place-name
API (see docs/API-NOTES.md). The examples are deliberately neutral: Røros, the
old copper-mining town, its 1860-1878 church book (source 6540), a family
from its 1865 census, and an 1894 history of the copper works. Digitalarkivet's
search pages are trimmed to their result lists (the full filter form is about
500 KB); one OCR line was dropped from the ALTO page.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from norway_archives_mcp import server
from norway_archives_mcp.client import NorHttp
from norway_archives_mcp.config import Config

FIXTURES = Path(__file__).parent / "fixtures"

SITE = "https://www.digitalarkivet.no"
VIEWER = "https://nye.digitalarkivet.no"
GOTO = "https://goto.digitalarkivet.no"
URN = "https://urn.digitalarkivet.no"
NB_API = "https://api.nb.no"
NB_IMAGES = "https://www.nb.no"
KARTVERKET = "https://api.kartverket.no"

#: The Røros church book's numbers, as the fixtures record them.
SOURCE = 6540
KB = "kb20070419660152"
KB_UUID = "fa741a35-09ec-4423-bfdf-ac9439347ed7"
FT = "ft20090803410602"
NB_ITEM = "6c40d98813a942688b706a97e15dde22"
NB_PAGE51 = "URN:NBN:no-nb_digibok_2009031803022_0061"

#: The smallest valid JPEG header a download check accepts.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def fixture(name: str) -> Any:
    """Load one recorded response: JSON for .json files, text otherwise."""
    path = FIXTURES / name
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def html(name: str) -> httpx.Response:
    """A recorded HTML page as a 200 response."""
    return httpx.Response(200, text=fixture(name), headers={"content-type": "text/html"})


def redirect(location: str, status: int = 303) -> httpx.Response:
    return httpx.Response(status, headers={"location": location})


def make_http(tmp_path: Path, **kwargs) -> NorHttp:
    """A client with no pacing and no back-off, caching under ``tmp_path``."""
    options: dict[str, Any] = {
        "backoff": 0.0,
        "intervals": {"digitalarkivet": 0.0, "nb": 0.0, "kartverket": 0.0},
    }
    options.update(kwargs)
    return NorHttp(tmp_path / "cache", **options)


@pytest.fixture
def http(tmp_path) -> NorHttp:
    return make_http(tmp_path)


@pytest.fixture
def served(tmp_path, monkeypatch) -> NorHttp:
    """Install a fast test client as the server's client for the duration of a test."""
    c = make_http(tmp_path)
    monkeypatch.setattr(server.runtime, "http", c)
    monkeypatch.setattr(server.runtime, "config", Config(cache_dir=tmp_path / "cache"))
    return c


@pytest.fixture
def download_dir(tmp_path, monkeypatch) -> Path:
    """A download folder the server is confined to."""
    folder = tmp_path / "images"
    folder.mkdir()
    monkeypatch.setattr(
        server.runtime, "config", Config(cache_dir=tmp_path / "cache", download_dir=folder)
    )
    return folder


async def call_tool(tool_name: str, /, **arguments) -> dict:
    """Invoke a tool the way a client does, so Field defaults are resolved."""
    result = await server.mcp.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)
