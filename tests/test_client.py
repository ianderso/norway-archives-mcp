"""The HTTP client: hosts, pacing, the daily budget, the cache, retries and downloads."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from norway_archives_mcp.client import HostNotAllowed, NorError, NorHttp, user_agent

from .conftest import JPEG, NB_API, SITE, make_http


class FakeClock:
    """A clock the client sleeps on, so pacing is measured without waiting."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 3))
        self.now += seconds


async def test_a_host_outside_the_services_is_refused(http):
    with pytest.raises(HostNotAllowed):
        await http.text("https://example.org/")
    with pytest.raises(HostNotAllowed):
        await http.text("http://www.digitalarkivet.no/")


@respx.mock
async def test_digitalarkivet_is_spaced_by_its_interval_and_others_are_not(tmp_path):
    clock = FakeClock()
    client = NorHttp(tmp_path / "c", da_interval=5.0, backoff=0.0, clock=clock, sleep=clock.sleep)
    respx.get(url__startswith=SITE).mock(return_value=httpx.Response(200, text="ok"))
    respx.get(url__startswith=NB_API).mock(return_value=httpx.Response(200, json={}))
    await client.text(f"{SITE}/a")
    await client.json(f"{NB_API}/x")
    await client.text(f"{SITE}/b")
    assert clock.slept == [5.0]
    assert client.calls_by_service == {"digitalarkivet": 2, "nb": 1}


@respx.mock
async def test_the_daily_budget_counts_live_requests_and_then_refuses(tmp_path):
    client = make_http(tmp_path, da_daily_budget=2)
    respx.get(url__startswith=SITE).mock(return_value=httpx.Response(200, text="ok"))
    await client.text(f"{SITE}/1")
    await client.text(f"{SITE}/2")
    with pytest.raises(NorError) as caught:
        await client.text(f"{SITE}/3")
    assert caught.value.code == "budget_spent"
    assert client.budget()["left"] == 0
    # The count survives a new client over the same cache folder.
    again = make_http(tmp_path, da_daily_budget=2)
    assert again.budget()["used"] == 2


@respx.mock
async def test_the_library_is_not_budgeted(tmp_path):
    client = make_http(tmp_path, da_daily_budget=1)
    respx.get(url__startswith=NB_API).mock(return_value=httpx.Response(200, json={}))
    for _ in range(3):
        await client.json(f"{NB_API}/x")


@respx.mock
async def test_memo_serves_a_cached_answer_and_never_caches_a_failure(http):
    calls = {"n": 0}

    async def make():
        calls["n"] += 1
        if calls["n"] == 1:
            raise NorError("timeout", "slow")
        return {"answer": calls["n"]}

    with pytest.raises(NorError):
        await http.memo("k", 1, make)
    assert await http.memo("k", 1, make) == {"answer": 2}
    assert await http.memo("k", 1, make) == {"answer": 2}
    assert http.cache_hits == 1
    assert await http.memo("k", 1, make, refresh=True) == {"answer": 3}


async def test_an_unreadable_cache_entry_is_fetched_again(http):
    async def make():
        return [1]

    await http.memo("k2", 1, make)
    for path in http.cache_dir.glob("*.json"):
        if "budget" not in path.name:
            path.write_text("{not json")
    assert await http.memo("k2", 1, make) == [1]


@respx.mock
async def test_a_redirect_inside_the_service_is_followed_and_outside_is_reported(http):
    respx.get(f"{SITE}/a").mock(return_value=httpx.Response(302, headers={"location": f"{SITE}/b"}))
    respx.get(f"{SITE}/b").mock(return_value=httpx.Response(200, text="here"))
    assert await http.text(f"{SITE}/a") == "here"
    respx.get(f"{SITE}/c").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.org/"})
    )
    with pytest.raises(NorError) as caught:
        await http.text(f"{SITE}/c")
    assert caught.value.code == "redirected"


@respx.mock
async def test_a_permalink_redirect_is_read_not_followed(http):
    respx.get("https://goto.digitalarkivet.no/kb1").mock(
        return_value=httpx.Response(
            303, headers={"location": "https://nye.digitalarkivet.no/source/1/parish/u"}
        )
    )
    assert await http.redirect_target("https://goto.digitalarkivet.no/kb1") == (
        "https://nye.digitalarkivet.no/source/1/parish/u"
    )
    respx.get("https://goto.digitalarkivet.no/kb2").mock(
        return_value=httpx.Response(200, text="<html>")
    )
    with pytest.raises(NorError) as caught:
        await http.redirect_target("https://goto.digitalarkivet.no/kb2")
    assert caught.value.code == "not_found"


@respx.mock
async def test_a_permalink_pointing_off_the_services_is_refused(http):
    respx.get("https://goto.digitalarkivet.no/kb3").mock(
        return_value=httpx.Response(303, headers={"location": "https://example.org/x"})
    )
    with pytest.raises(HostNotAllowed):
        await http.redirect_target("https://goto.digitalarkivet.no/kb3")


@respx.mock
async def test_a_503_gets_one_retry(http):
    route = respx.get(f"{NB_API}/r").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})]
    )
    assert await http.json(f"{NB_API}/r") == {"ok": 1}
    assert route.call_count == 2


@respx.mock
async def test_a_404_is_not_found_and_not_retried(http):
    route = respx.get(f"{NB_API}/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(NorError) as caught:
        await http.json(f"{NB_API}/missing")
    assert caught.value.code == "not_found" and route.call_count == 1


@respx.mock
async def test_a_bot_check_is_reported_as_one(http):
    respx.get(f"{SITE}/x").mock(
        return_value=httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="<html>")
    )
    with pytest.raises(NorError) as caught:
        await http.text(f"{SITE}/x")
    assert caught.value.code == "challenge"


@respx.mock
async def test_non_json_is_reported(http):
    respx.get(f"{NB_API}/html").mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(NorError) as caught:
        await http.json(f"{NB_API}/html")
    assert caught.value.code == "unexpected_page"


@respx.mock
async def test_download_writes_a_new_jpeg_and_never_overwrites(http, tmp_path):
    respx.get(f"{NB_API}/img").mock(return_value=httpx.Response(200, content=JPEG))
    target = tmp_path / "page.jpg"
    written, kind = await http.download(f"{NB_API}/img", target)
    assert (written, kind) == (len(JPEG), "jpeg") and target.read_bytes() == JPEG
    with pytest.raises(FileExistsError):
        await http.download(f"{NB_API}/img", target)


@respx.mock
async def test_download_refuses_what_is_not_a_jpeg(http, tmp_path):
    respx.get(f"{NB_API}/page").mock(return_value=httpx.Response(200, text="<html>error"))
    target = tmp_path / "x.jpg"
    with pytest.raises(NorError) as caught:
        await http.download(f"{NB_API}/page", target)
    assert caught.value.code == "not_an_image" and not target.exists()
    respx.get(f"{NB_API}/png").mock(
        return_value=httpx.Response(200, content=b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    )
    with pytest.raises(NorError) as caught:
        await http.download(f"{NB_API}/png", target)
    assert caught.value.code == "extension_mismatch" and not target.exists()


@respx.mock
async def test_an_oversized_answer_is_refused(http):
    respx.get(f"{NB_API}/big").mock(
        return_value=httpx.Response(200, headers={"content-length": "99999999999"}, text="x")
    )
    with pytest.raises(NorError) as caught:
        await http.json(f"{NB_API}/big")
    assert caught.value.code == "too_large"


def test_the_user_agent_names_the_project_and_the_contact():
    agent = user_agent("me@example.org")
    assert agent.startswith("norway-archives-mcp/") and "github.com/ianderso" in agent
    assert agent.endswith("; me@example.org)")


async def test_concurrent_identical_calls_share_one_make(http):
    import asyncio

    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    async def make():
        calls["n"] += 1
        started.set()
        await release.wait()
        return {"v": 1}

    first = asyncio.create_task(http.memo("same", 1, make))
    await started.wait()
    second = asyncio.create_task(http.memo("same", 1, make))
    await asyncio.sleep(0)
    release.set()
    assert await first == await second == {"v": 1}
    assert calls["n"] == 1 and http.shared_waits == 1


def test_the_cache_holds_parsed_answers_not_pages(tmp_path):
    client = make_http(tmp_path)
    client._cache_put("abc", {"small": True})
    stored = json.loads((tmp_path / "cache" / "abc.json").read_text())
    assert stored["data"] == {"small": True}
