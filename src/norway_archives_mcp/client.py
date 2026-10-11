"""Polite, cached async HTTP for three Norwegian public services.

Every request goes to a public archive's or library's own servers, so the
client is a careful guest:

* **Only known hosts.** A request hook refuses any host outside the three
  services' fixed addresses, so an address taken from a response or written
  by injected text cannot send a request anywhere else. Redirects are followed
  by hand, and only between one service's own hosts.
* **One request at a time per service, spaced.** Digitalarkivet asks crawlers
  for five seconds between requests, and gets at least that; the National
  Library's API gets one second and Kartverket's half a second. Services are
  independent, so a library search does not wait behind an archive page.
* **A daily budget for Digitalarkivet.** Live requests to it are counted per
  UTC day, across restarts, and refused once the budget is spent. Cached
  answers cost nothing.
* **Bounded answers.** A page over ``MAX_TEXT_BYTES`` or an image over
  ``MAX_IMAGE_BYTES`` is refused as it streams in.
* **Identical concurrent calls share one request.**
* **Parsed answers are cached on disk,** keyed by the request, for as many days
  as the caller says (:meth:`NorHttp.memo`). Only what the tools return is
  kept, not whole pages. A failure is never cached.
* **A 429, a 5xx or a dropped connection gets one retry,** honouring
  ``Retry-After`` up to 30 seconds.
* **An honest User-Agent** naming the package, its version and its home.
"""

from __future__ import annotations

import asyncio
import email.utils
import hashlib
import json
import logging
import os
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from . import __version__

logger = logging.getLogger("norway_archives_mcp.client")

#: Where the project lives; named in the User-Agent so a site can see who calls.
PROJECT_URL = "https://github.com/ianderso/norway-archives-mcp"

#: Longest wait honoured from a ``Retry-After`` header, in seconds.
RETRY_AFTER_CAP = 30.0

#: Redirect hops followed inside one service.
MAX_REDIRECTS = 3

#: A web page, JSON answer or ALTO file larger than this is refused. The
#: largest seen, Digitalarkivet's person-search page with its full filter
#: form, is about 550 KB; a 500-image book's IIIF manifest is about 750 KB.
MAX_TEXT_BYTES = 8_000_000

#: An image larger than this is not written. A full-resolution church-book
#: spread (about 5,000 x 3,900 pixels) is 4-8 MB as JPEG.
MAX_IMAGE_BYTES = 60_000_000

#: Read timeout for one image download, in seconds.
DOWNLOAD_TIMEOUT = 120.0

#: Image formats by their file suffixes; the image tools save JPEG only.
IMAGE_SUFFIXES = {"jpeg": (".jpg", ".jpeg")}

_DAY = 86_400.0


@dataclass(frozen=True)
class Service:
    """One of the three services: its hosts and the spacing between requests."""

    key: str
    name: str
    hosts: frozenset[str]
    interval: float
    budgeted: bool = False


def services(da_interval: float) -> dict[str, Service]:
    """The fixed services, with Digitalarkivet's spacing as configured."""
    return {
        "digitalarkivet": Service(
            "digitalarkivet",
            "Digitalarkivet",
            frozenset(
                {
                    "www.digitalarkivet.no",
                    "nye.digitalarkivet.no",
                    "goto.digitalarkivet.no",
                    "urn.digitalarkivet.no",
                    # Never fetched: the classic site's page permalinks
                    # redirect here, and the address is read for its numbers.
                    "media.digitalarkivet.no",
                }
            ),
            da_interval,
            budgeted=True,
        ),
        "nb": Service("nb", "Nasjonalbiblioteket", frozenset({"api.nb.no", "www.nb.no"}), 1.0),
        "kartverket": Service("kartverket", "Kartverket", frozenset({"api.kartverket.no"}), 0.5),
    }


class NorError(RuntimeError):
    """A request that did not produce a usable answer.

    ``code`` is one of: ``http_error``, ``not_found``, ``rate_limited``,
    ``timeout``, ``no_response``, ``too_large``, ``redirected``,
    ``challenge``, ``budget_spent``, ``not_an_image``, ``extension_mismatch``,
    ``unexpected_page``.
    """

    def __init__(
        self, code: str, detail: str, *, status: int = 0, url: str = "", location: str = ""
    ):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status
        self.url = url
        self.location = location


class HostNotAllowed(RuntimeError):
    """A request to a host outside the three services."""


def user_agent(contact: str = "") -> str:
    """The User-Agent: package, version, project address, and the operator's contact."""
    extra = f"; {contact}" if contact else ""
    return f"norway-archives-mcp/{__version__} (+{PROJECT_URL}{extra})"


def sniff_format(head: bytes) -> str:
    """Name an image format from its first bytes, or ``unknown``."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return "unknown"


class NorHttp:
    """Cached, paced async HTTP for Digitalarkivet, the National Library and Kartverket.

    Parameters
    ----------
    cache_dir : Path
        Directory for cached answers and the daily request count.
    timeout : float, optional
        Per-request timeout in seconds.
    da_interval : float, optional
        Least seconds between two Digitalarkivet requests.
    da_daily_budget : int, optional
        Live Digitalarkivet requests allowed per UTC day.
    contact : str, optional
        Appended to the User-Agent.
    retries : int, optional
        Further attempts after a 429, a 5xx or a dropped connection.
    backoff : float, optional
        Base of the wait between attempts when no ``Retry-After`` is given.
    intervals : dict, optional
        For tests: override the spacing of any service by key.
    transport : httpx.AsyncBaseTransport, optional
        For tests.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        timeout: float = 30.0,
        da_interval: float = 5.0,
        da_daily_budget: int = 600,
        contact: str = "",
        retries: int = 1,
        backoff: float = 1.0,
        intervals: dict[str, float] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._cache_dir = cache_dir
        self._timeout = timeout
        self._budget = da_daily_budget
        self._retries = retries
        self._backoff = backoff
        self._clock = clock
        self._sleep = sleep
        self._services = services(da_interval)
        for key, value in (intervals or {}).items():
            svc = self._services[key]
            self._services[key] = Service(svc.key, svc.name, svc.hosts, value, svc.budgeted)
        self._by_host = {h: s for s in self._services.values() for h in s.hosts}
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent(contact)},
            event_hooks={"request": [self._only_known_hosts]},
            follow_redirects=False,
            transport=transport,
        )
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._live_calls = 0
        self._cache_hits = 0
        self._shared_waits = 0
        self._calls_by_service: dict[str, int] = {}
        self._last_error: dict | None = None

    # ------------------------------------------------------------------ #
    # Counters
    # ------------------------------------------------------------------ #
    @property
    def live_calls(self) -> int:
        """int: Requests sent this session, retries and downloads included."""
        return self._live_calls

    @property
    def cache_hits(self) -> int:
        """int: Answers served from the disk cache this session."""
        return self._cache_hits

    @property
    def shared_waits(self) -> int:
        """int: Calls answered by joining an identical request already in flight."""
        return self._shared_waits

    @property
    def calls_by_service(self) -> dict[str, int]:
        """dict: Live requests this session, by service."""
        return dict(self._calls_by_service)

    @property
    def last_error(self) -> dict | None:
        """dict or None: The most recent failure this session."""
        return self._last_error

    @property
    def cache_dir(self) -> Path:
        """Path: Where answers are cached."""
        return self._cache_dir

    def budget(self) -> dict:
        """Digitalarkivet's daily budget: the day (UTC), requests used and left."""
        day, used = self._budget_read()
        return {
            "day": day,
            "used": used,
            "limit": self._budget,
            "left": max(0, self._budget - used),
        }

    # ------------------------------------------------------------------ #
    # Lifecycle and the host allowlist
    # ------------------------------------------------------------------ #
    async def aclose(self) -> None:
        """Close the HTTP transport."""
        await self._http.aclose()

    async def __aenter__(self) -> NorHttp:
        """Return the client."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Close the transport."""
        await self.aclose()

    async def _only_known_hosts(self, request: httpx.Request) -> None:
        """Refuse any request that is not https to one of the services' hosts."""
        host = request.url.host.lower()
        if request.url.scheme != "https" or host not in self._by_host:
            raise HostNotAllowed(
                f"refusing a request to {host!r}: this server reaches only Digitalarkivet, "
                "the National Library and Kartverket"
            )

    def service_of(self, url: str) -> Service:
        """The service an address belongs to.

        Raises
        ------
        HostNotAllowed
            If the address is not https or not on one of the services' hosts.
        """
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or host not in self._by_host:
            raise HostNotAllowed(
                f"refusing {url[:120]!r}: this server reaches only Digitalarkivet, "
                "the National Library and Kartverket over https"
            )
        return self._by_host[host]

    # ------------------------------------------------------------------ #
    # Requests
    # ------------------------------------------------------------------ #
    async def memo(
        self,
        key: str,
        ttl_days: float,
        make: Callable[[], Awaitable[Any]],
        *,
        refresh: bool = False,
    ) -> Any:
        """Return a cached answer for ``key``, or build, cache and return a new one.

        ``make`` fetches and parses; whatever it returns must be JSON-serialisable.
        Concurrent calls for the same key share one ``make``. A failure is
        never cached.
        """
        cache_key = _key(key)
        if not refresh:
            cached = self._cache_get(cache_key, ttl_days * _DAY)
            if cached is not None:
                self._cache_hits += 1
                return cached
        data = await self._shared(cache_key, make)
        self._cache_put(cache_key, data)
        return data

    async def text(self, url: str, *, accept: str = "text/html") -> str:
        """GET an address and return the body as text.

        Raises
        ------
        NorError
            On a status of 400 or more, no response, a bot check, a redirect
            outside the service, a spent budget, or an answer over the size
            limit.
        """
        response = await self._send(url, limit=MAX_TEXT_BYTES, headers={"Accept": accept})
        return response.text

    async def json(self, url: str) -> Any:
        """GET an address and decode its JSON body."""
        response = await self._send(
            url, limit=MAX_TEXT_BYTES, headers={"Accept": "application/json"}
        )
        try:
            return response.json()
        except ValueError:
            error = NorError(
                "unexpected_page",
                "the service answered with something that is not JSON",
                status=response.status_code,
                url=url,
            )
            self._note(error)
            raise error from None

    async def redirect_target(self, url: str) -> str:
        """GET an address that answers with a redirect, and return where it points.

        Used for Digitalarkivet's ``goto`` permalinks, whose answer *is* the
        redirect: the target is read, not followed.

        Raises
        ------
        NorError
            ``not_found`` if the address does not redirect (an unknown
            permalink answers with a page instead).
        """
        service = self.service_of(url)
        response = await self._retrying(
            url, lambda: self._paced(service, url, limit=MAX_TEXT_BYTES)
        )
        if response.status_code in (301, 302, 303, 307, 308):
            location = urljoin(url, response.headers.get("location", ""))
            self.service_of(location)
            return location
        error = NorError(
            "not_found",
            "this permalink does not lead to a scanned page",
            status=response.status_code,
            url=url,
        )
        self._note(error)
        raise error

    async def download(
        self, url: str, target: Path, *, max_bytes: int = MAX_IMAGE_BYTES
    ) -> tuple[int, str]:
        """Write an image to a new file.

        Nothing is written unless the bytes are a JPEG and ``target`` ends in
        a JPEG suffix. The file is created exclusively, so an existing one is
        never overwritten, and removed again if writing fails.

        Returns
        -------
        tuple of (int, str)
            Bytes written, and the format named by :func:`sniff_format`.

        Raises
        ------
        NorError
            If the service refuses, sends something that is not an image
            (``not_an_image``), an image of another format (``extension_mismatch``),
            or more than ``max_bytes`` (``too_large``). Nothing is left on disk.
        FileExistsError
            If ``target`` exists. It is left untouched.
        """
        response = await self._send(
            url,
            limit=max_bytes,
            headers={"Accept": "image/jpeg"},
            timeout=httpx.Timeout(self._timeout, read=DOWNLOAD_TIMEOUT),
        )
        body = response.content
        kind = sniff_format(body[:16])
        if kind == "unknown":
            raise NorError(
                "not_an_image",
                "the service answered with something that is not an image "
                f"({response.headers.get('content-type', 'no content type')}); nothing was saved",
                status=response.status_code,
                url=url,
            )
        if target.suffix.lower() not in IMAGE_SUFFIXES.get(kind, ()):
            raise NorError(
                "extension_mismatch",
                f"the service sent a {kind.upper()} image, which cannot be saved as "
                f"{target.name}; nothing was saved",
                status=response.status_code,
                url=url,
            )
        out = target.open("xb")
        try:
            with out:
                out.write(body)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return len(body), kind

    async def _send(self, url: str, *, limit: int, **kwargs) -> httpx.Response:
        """One GET, paced, budgeted, retried, redirected within its service by hand."""
        service = self.service_of(url)
        return await self._retrying(
            url, lambda: self._follow(service, url, limit=limit, **kwargs), final=True
        )

    async def _retrying(
        self, url: str, attempt_once: Callable[[], Awaitable[httpx.Response]], *, final=False
    ) -> httpx.Response:
        """Run one attempt, retrying a 429, a 5xx or a dropped connection."""
        attempt = 0
        while True:
            try:
                response = await attempt_once()
            except NorError as exc:
                error = exc
                response = None
            else:
                if response.status_code < 400:
                    return response
                error = _http_error(response, url)
            retryable = error.code in ("no_response", "rate_limited") or error.status >= 500
            if not retryable or attempt >= self._retries:
                self._note(error)
                raise error
            attempt += 1
            wait = _retry_after(response)
            if wait is None:
                wait = self._backoff * 2 ** (attempt - 1) + random.uniform(0, self._backoff / 2)
            wait = min(wait, RETRY_AFTER_CAP)
            logger.info("%s -> %s; retry %d in %.1fs", url, error.code, attempt, wait)
            await self._sleep(wait)

    async def _follow(self, service: Service, url: str, *, limit: int, **kwargs) -> httpx.Response:
        """Send, following redirects only between the service's own hosts."""
        for _ in range(MAX_REDIRECTS + 1):
            response = await self._paced(service, url, limit=limit, **kwargs)
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = urljoin(url, response.headers.get("location", ""))
            target = urlsplit(location)
            if target.scheme != "https" or (target.hostname or "").lower() not in service.hosts:
                raise NorError(
                    "redirected",
                    f"the service redirects this request to {location}",
                    status=response.status_code,
                    url=url,
                    location=location,
                )
            url = location
        raise NorError("redirected", "too many redirects", url=url)

    async def _paced(self, service: Service, url: str, *, limit: int, **kwargs) -> httpx.Response:
        """Send one request once the service's turn, interval and budget allow."""
        lock = self._locks.setdefault(service.key, asyncio.Lock())
        async with lock:
            if service.budgeted:
                self._budget_spend(url)
            last = self._last.get(service.key)
            if last is not None:
                wait = service.interval - (self._clock() - last)
                if wait > 0:
                    await self._sleep(wait)
            self._last[service.key] = self._clock()
            self._live_calls += 1
            self._calls_by_service[service.key] = self._calls_by_service.get(service.key, 0) + 1
            try:
                async with self._http.stream("GET", url, **kwargs) as response:
                    body = await _read_capped(response, limit, url)
                return _with_body(response, body)
            except httpx.TimeoutException as exc:
                raise NorError("timeout", _transport_text(exc), url=url) from None
            except httpx.TransportError as exc:
                raise NorError("no_response", _transport_text(exc), url=url) from None

    # ------------------------------------------------------------------ #
    # Daily budget
    # ------------------------------------------------------------------ #
    def _budget_path(self) -> Path:
        return self._cache_dir / "digitalarkivet-budget.json"

    def _budget_read(self) -> tuple[str, int]:
        today = datetime.now(UTC).date().isoformat()
        try:
            data = json.loads(self._budget_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return today, 0
        if not isinstance(data, dict) or data.get("day") != today:
            return today, 0
        used = data.get("used")
        return today, used if isinstance(used, int) and used >= 0 else 0

    def _budget_spend(self, url: str) -> None:
        day, used = self._budget_read()
        if used >= self._budget:
            error = NorError(
                "budget_spent",
                f"today's {self._budget} live requests to Digitalarkivet are used (the day "
                "runs on UTC); cached answers still work",
                url=url,
            )
            self._note(error)
            raise error
        try:
            _write_atomically(self._budget_path(), json.dumps({"day": day, "used": used + 1}))
        except OSError:
            logger.warning("could not record the Digitalarkivet request count")

    # ------------------------------------------------------------------ #
    # Shared machinery
    # ------------------------------------------------------------------ #
    async def _shared(self, key: str, make: Callable[[], Awaitable[Any]]) -> Any:
        """Run ``make`` once for concurrent callers asking the same thing."""
        if (pending := self._inflight.get(key)) is not None:
            self._shared_waits += 1
            return await asyncio.shield(pending)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            data = await make()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            # Mark it retrieved: a failure nobody else was waiting on must
            # not be logged as "exception was never retrieved".
            future.exception()
            raise
        else:
            future.set_result(data)
            return data
        finally:
            self._inflight.pop(key, None)

    def _note(self, error: NorError) -> None:
        self._last_error = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "error": error.code,
            "status": error.status or None,
            "detail": error.detail[:300],
            "request": error.url[:300],
        }

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _cache_get(self, key: str, ttl: float) -> Any:
        """Return a cached answer, or None if absent, expired or unreadable."""
        path = self._cache_path(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, ValueError):
            # A truncated or hand-edited entry is a re-fetch, not a crash.
            logger.warning("discarding unreadable cache entry %s", path.name)
            return None
        if not isinstance(entry, dict) or "data" not in entry:
            return None
        stored = entry.get("stored")
        if not isinstance(stored, int | float) or time.time() - stored > ttl:
            return None
        return entry["data"]

    def _cache_put(self, key: str, data: Any) -> None:
        try:
            _write_atomically(
                self._cache_path(key), json.dumps({"stored": time.time(), "data": data})
            )
        except (OSError, TypeError, ValueError):
            # A cache that cannot be written costs speed, not correctness.
            logger.warning("could not write the response cache in %s", self._cache_dir)


async def _read_capped(response: httpx.Response, limit: int, url: str) -> bytes:
    """Read a streamed body, refusing it once it passes ``limit`` bytes."""
    too_large = NorError(
        "too_large",
        f"the answer is over {limit / 1_000_000:g} MB, more than this server reads",
        status=response.status_code,
        url=url,
    )
    declared = response.headers.get("content-length", "").strip()
    if declared.isdigit() and int(declared) > limit:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def _with_body(response: httpx.Response, body: bytes) -> httpx.Response:
    """A complete response carrying ``body``, already decoded, in place of the stream."""
    spent = {"content-encoding", "content-length", "transfer-encoding"}
    return httpx.Response(
        response.status_code,
        headers=[(k, v) for k, v in response.headers.multi_items() if k.lower() not in spent],
        content=body,
        request=response.request,
        extensions=response.extensions,
    )


def _http_error(response: httpx.Response, url: str) -> NorError:
    """Classify a 4xx or 5xx answer."""
    status = response.status_code
    if response.headers.get("cf-mitigated", "").lower() == "challenge":
        return NorError(
            "challenge",
            "the service answered with a bot check; open the page in a browser",
            status=status,
            url=url,
        )
    if status == 429:
        return NorError(
            "rate_limited", "the service asked for fewer requests", status=status, url=url
        )
    if status == 404:
        return NorError(
            "not_found", "the service has nothing at this address", status=status, url=url
        )
    text = response.text.strip()
    if text[:1] == "<":
        detail = response.reason_phrase or "an HTML error page"
    else:
        detail = " ".join(text.split())[:300] or response.reason_phrase
    return NorError("http_error", detail, status=status, url=url)


def _transport_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".rstrip(": ")


def _retry_after(response: httpx.Response | None) -> float | None:
    """Seconds a ``Retry-After`` header asks for, or None if absent or unreadable."""
    if response is None:
        return None
    raw = (response.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _write_atomically(path: Path, text: str) -> None:
    """Write a file so a reader never sees it half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
