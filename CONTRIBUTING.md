# Contributing

Issues and pull requests are welcome. This file says how the project is put
together and what a change is expected to carry.

## Setting up

```bash
git clone https://github.com/ianderso/norway-archives-mcp
cd norway-archives-mcp
uv sync --extra dev
```

Before sending a change, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The suite is mocked with [respx](https://lundberg.github.io/respx/) against
recorded responses. It must never touch a live service: each one is a public
archive's or library's own server, and CI should not depend on any of them
being up.

## Where things live

| Path | What it holds |
| --- | --- |
| `src/norway_archives_mcp/server.py` | The tools. Their docstrings and `Field` descriptions *are* the published tool descriptions and schema. Also the download destination rules. |
| `src/norway_archives_mcp/digitalarkivet.py` | Digitalarkivet's addresses, the HTML parsers for its search, record and source pages, and the IIIF manifest reader. |
| `src/norway_archives_mcp/nb.py` | The National Library's API: search, snippets, the IIIF 2 manifest, and ALTO text. |
| `src/norway_archives_mcp/places.py` | Kartverket's place-name API, and the historical municipality and list-type codes. |
| `src/norway_archives_mcp/data/digitalarkivet_codes.json` | Those codes, read from Digitalarkivet's search form. |
| `src/norway_archives_mcp/client.py` | The cached, paced HTTP client: fixed hosts, per-service spacing, the daily budget, the size caps. |
| `src/norway_archives_mcp/config.py` | Settings from the environment and `.env`. |
| `docs/API-NOTES.md` | What each service was observed to do, and when. |
| `docs/DESIGN.md` | Why the server is shaped the way it is, and what is out of scope by decision. |
| `tests/fixtures/` | Recorded responses and the tool-schema snapshot. |
| `tests/test_tool_contract.py` | Tests over the tool surface as a client sees it. |
| `tests/live_check.py` | The one script that talks to live services, run by hand. Not collected. |

## What a change carries

**A test that fails without it.** Bug fixes especially: reproduce the bug as a
test first.

**Descriptions written for the model.** A tool's docstring is what a model
reads when choosing and calling it. The combined descriptions have a ceiling
(`DESCRIPTION_BUDGET` in `tests/test_tool_contract.py`), because they are sent
on every session. Raise it deliberately, in a pull request of its own.

**The evidence distinction, kept.** A transcription, a snippet or OCR text is
a lead to the scanned page, never the record. Tools that return text say so.

**A citation on every page.** Any result that names a scanned page carries its
source, archive reference, image number, permanent id and permalink.

**A structured result, never an exception.** Every tool catches its failures
and returns an `error` envelope.

**Nothing that writes to a service, logs in, or works around a bot check or an
access rule.** See [docs/DESIGN.md](docs/DESIGN.md#out-of-scope-by-decision).

**No faster than the services ask.** Digitalarkivet's floor of five seconds
between requests is not configurable downward.

**A new fixture recorded, not invented,** when a change depends on how a
service answers, with what was observed and when added to `docs/API-NOTES.md`.
Keep fixtures to historical records and neutral examples.

**The snapshot, when the surface changes.** Renaming or adding a tool or a
parameter fails the snapshot test on purpose. Regenerate it with
`uv run python -m tests.regen_tool_snapshot`, update the README tables, and add
a `CHANGELOG.md` entry.

## When Digitalarkivet changes a page

The parsers read the English pages by their CSS classes and labels. If
`tests.live_check` reports `page_changed`, record the new page as a fixture,
fix the parser against it, and note the date in `docs/API-NOTES.md`.

## Releasing

A maintainer bumps `__version__` in `src/norway_archives_mcp/__init__.py` and
both versions in `server.json`, moves the changelog's Unreleased entries under
the new version, and publishes a GitHub release tagged `v<version>`. The
release workflow builds the tag, publishes to PyPI by Trusted Publishing, and
lists the version in the MCP Registry.
