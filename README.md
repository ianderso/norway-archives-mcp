# norway-archives-mcp

[![CI](https://github.com/ianderso/norway-archives-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/norway-archives-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/norway-archives-mcp)](https://pypi.org/project/norway-archives-mcp/)

<!-- mcp-name: io.github.ianderso/norway-archives-mcp -->

An [MCP](https://modelcontextprotocol.io) server for **Norwegian family
history**: the National Archives' church books, censuses and emigrant lists
and their scans, the National Library's books and newspapers, and today's
official place names.

- **[Digitalarkivet](https://www.digitalarkivet.no)**, run by Nasjonalarkivet
  (the National Archives of Norway), holds the parish registers
  (*ministerialbøker* and *klokkerbøker*), the censuses of 1801–1920, emigrant
  protocols, probate records and much more. Some of it is transcribed and
  searchable; far more is scanned and can only be read page by page. The
  server does both: it searches the transcriptions, maps a scanned book's lists
  (baptisms, confirmations, marriages, burials, in- and out-migration) to
  image numbers, and downloads a page with its permanent id.
- **[Nasjonalbiblioteket](https://www.nb.no)** (the National Library) has
  digitised nearly every Norwegian book and newspaper, including the
  *bygdebøker*, the farm-by-farm local histories genealogists live in. Many
  open only from Norwegian addresses, but a search still tells you which page
  a name is on.
- **[Kartverket](https://www.kartverket.no)**'s place-name register gives
  today's spelling, type and coordinates of a farm or hamlet.

It works the way a careful genealogist does. **The scanned page is the
evidence.** A transcription is a lead (most church-book transcriptions were
keyed by contractors for Ancestry, MyHeritage and FamilySearch), and a search
that finds nothing has only searched what was transcribed. Every page comes
back with its source, archive reference, image number and permanent link, so
the citation points at the archive, not at this server.

Nothing here writes anywhere but your own disk, and nothing here keeps a
family tree.

## Tools

The server publishes thirteen tools. All but the two downloads are read-only;
those create one new file each and never overwrite one.

| Tool | What it does |
| --- | --- |
| `da_search_persons` | Search Digitalarkivet's transcribed records by name, historical municipality, list type and years. |
| `da_get_record` | Read one record: its fields, everyone named in it, its source, and the permanent id of its scanned page. |
| `da_search_sources` | Find sources by place, period and list, with which lists are scanned and which are searchable. |
| `da_get_source` | Describe one source and map its scans: archive reference, image count, and the image each list starts on. |
| `da_list_pages` | List a source's pages in order, optionally from the start of one list, with permanent ids and links. |
| `da_download_page` | Download one scanned page (church book, census, anything with a page id) with its citation. |
| `nb_search` | Search the National Library's books, newspapers, journals, maps and more. |
| `nb_search_inside` | Find the pages of one item that mention a word, with snippets and printed page numbers. |
| `nb_get_page` | Read one page of an item: its OCR text where the item is open, and its citation. |
| `nb_download_page` | Download one page image of an item that is open where you are. |
| `place_names` | Search Kartverket's register of official place names (farms, hamlets, lakes, mountains). |
| `municipalities` | Look up Digitalarkivet's historical municipalities and their numbers, and the list-type codes. No network. |
| `cache_status` | This session's requests, Digitalarkivet's daily budget, and cache use. No network. |

A typical path through an untranscribed list (confirmations, say):

1. `da_search_sources(municipality="Røros", list_type="kf")` finds the church
   books that hold confirmations, and says the confirmations are scanned but
   not searchable.
2. `da_get_source(source_id=6540)` gives the image the confirmations start on.
3. `da_list_pages(source_id=6540, section="kf")` lists those pages with their
   permanent ids.
4. `da_download_page(page_id="kb2007…", destination=…)` saves each page to read,
   with a citation such as *Church book from Røros parish 1860-1878 (1640P),
   AV/SAT-A-1456/681/L0932, image 171 of 464 (kb20070419660172). Nasjonalarkivet
   (The National Archives of Norway), Digitalarkivet.
   https://goto.digitalarkivet.no/kb20070419660172*.

## Setup

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/). There is
no key to request.

**Without cloning.** `uvx` fetches it from PyPI and runs it in one step:

```bash
uvx norway-archives-mcp
```

**From a clone**, which is what you want if you will change it:

```bash
git clone https://github.com/ianderso/norway-archives-mcp
cd norway-archives-mcp
uv sync
uv run norway-archives-mcp   # stdio server, usually launched by the client
```

Either way the server speaks MCP over stdio, so you will normally let an MCP
client start it rather than run it by hand.

### Claude Desktop

```json
{
  "mcpServers": {
    "norway-archives": {
      "command": "uvx",
      "args": ["norway-archives-mcp"]
    }
  }
}
```

A desktop app does not always inherit your shell's `PATH`. If the server fails
to start because `uvx` cannot be found, give the full path that `which uvx`
prints as the `command`.

### Claude Code

```bash
claude mcp add norway-archives -- uvx norway-archives-mcp
```

## Configuration

Nothing is required. A `.env` file in the directory the server starts in
supplies anything the environment does not; only that directory is read.

| Variable | Meaning |
| --- | --- |
| `NORWAY_ARCHIVES_CACHE_DIR` | Cache directory, which also holds the daily request count. Default `~/.cache/norway-archives-mcp`. |
| `NORWAY_ARCHIVES_TIMEOUT` | HTTP timeout in seconds for one request. Default 30. Image downloads get 120 to read. |
| `NORWAY_ARCHIVES_DA_INTERVAL` | Least seconds between two Digitalarkivet requests. Default 5, and never below 5. |
| `NORWAY_ARCHIVES_DA_DAILY_BUDGET` | Most live Digitalarkivet requests per UTC day. Default 600. Cached answers are free. |
| `NORWAY_ARCHIVES_CONTACT` | An email address or URL added to the User-Agent, so an archive can reach you if your use causes trouble. Optional, and courteous. |
| `NORWAY_ARCHIVES_DOWNLOAD_DIR` | An existing folder. When set, the downloads save only inside it. Set it to save into an iCloud Drive folder, which lives under `~/Library`. |

An unusable value is reported on the first tool call as a `not_configured`
result naming the variable.

## Being a good guest, and what the terms say

**Digitalarkivet** publishes no API and no terms-of-use page; its footer
links only privacy and accessibility statements. Its reuse page says scans
without restrictions "kan disse fritt brukes videre både i trykksaker og på
internett": they may be freely reused in print and online, with the holding
archive credited
([digitalarkivet.no/content/1570](https://www.digitalarkivet.no/content/1570)).
Its `robots.txt` asks every crawler for five seconds between requests and
disallows a list of named bots, AI agents among them. This server is not a
crawler: it fetches the pages a researcher asks for, one at a time, at least
five seconds apart (configurable upward only), within a daily budget, with a
User-Agent that names it. Search, record and source pages are cached as
parsed results for 1, 30 and 30 days; manifests for 30; permalink lookups for
a year.

**The National Library's API** is documented and keyless
([api.nb.no](https://api.nb.no)). Access to each item follows the library's
own rules: material marked for Norway opens only from Norwegian addresses
(foreign researchers can apply for access to the Bokhylla collection), and
this server reports that rather than working around it. One request a second.

**Kartverket's place-name API** needs no login or authorisation, in its own
words "ikke nødvendig med innlogging/autorisasjon"
([api.kartverket.no/stedsnavn](https://api.kartverket.no/stedsnavn/v1/)).
Two requests a second at most.

A 429, a 5xx or a dropped connection gets one retry, honouring `Retry-After`.
A bot check is reported as `blocked` and left alone.

## How to read what comes back

- **A transcription is not the record.** Read the scanned page
  (`da_download_page`) before citing a name, a date or a relationship.
- **A zero is narrow.** `da_search_persons` searches transcribed lists only.
  `da_search_sources` shows which lists are scanned but not searchable;
  confirmations and migration lists often are. Page through them.
- **Municipalities moved.** The `da_` tools filter by the historical
  municipalities Digitalarkivet uses (see `municipalities`); `place_names`
  reports today's, after the mergers of 2020 and earlier.
- **Section boundaries are approximate.** `da_get_source` gives the image a
  list starts on; it usually runs until the next list starts, but books were
  not always kept in order.
- **Norway-only books still answer.** `nb_search_inside` gives the printed
  page number of a hit even where the page cannot be shown here.
- **Census pages** (ids beginning `ft`) come from the older viewer at full
  resolution only.

## Deliberately not here

- **Writing anything, or logging in.** No tool sends a correction, a report or
  a message to any service.
- **The Norwegian Historical Population Register (HBR)**, whose search is a
  form and whose API is for partners.
- **Norway Heritage**, whose terms forbid duplication or redistribution
  without permission.
- **Working around access rules**: Norway-only material, restricted recent
  records, or bot checks.

## Security

Tool arguments are written by a model, and the model reads text this server
does not control: record transcriptions, catalogue entries, OCR. The server
assumes that text can steer the model, and limits what a steered model can
make it do.

- **Which hosts.** Requests go only to the three services' fixed hosts over
  https. Any other host is refused, including addresses taken from a response.
  Redirects are followed only within one service.
- **How much.** A page or JSON answer over 8 MB, or an image over 60 MB, is
  refused as it streams in.
- **Which files.** The downloads create one new file and never overwrite one.
  The bytes must be a JPEG, judged by their first bytes, and the file must end
  in `.jpg` or `.jpeg`. Never a hidden file or folder, never under `~/Library`,
  and with `NORWAY_ARCHIVES_DOWNLOAD_DIR` set, never outside it, all judged
  after links are resolved. A refused download leaves nothing on disk.
- **Arguments are validated** (page ids, item ids, record addresses) before
  they reach a request.
- **Site text is untrusted.** The server's instructions tell the model to
  treat record and catalogue text as material to weigh, never as instructions.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches a site
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # paced calls to the live services
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how the suite is organised,
[docs/API-NOTES.md](docs/API-NOTES.md) for what was observed of each service
and when, and [docs/DESIGN.md](docs/DESIGN.md) for why the server is shaped
this way.

## Credits

The records, scans and catalogue belong to Nasjonalarkivet,
Nasjonalbiblioteket and Kartverket. Most church-book transcriptions were made
by AMF (Ancestry, MyHeritage and FamilySearch) under agreement with the
National Archives.

## License

[MIT](LICENSE).
