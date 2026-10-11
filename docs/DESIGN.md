# Design

Why the server is shaped the way it is. What each service was seen to do is in
[API-NOTES.md](API-NOTES.md).

## One server, three services

A Norwegian line needs all three in one sitting: Kartverket to find the farm,
Digitalarkivet for the church books and censuses that name the family, and the
National Library for the *bygdebok* that already traced it. They share
nothing technically, so each has its own module (`digitalarkivet.py`, `nb.py`,
`places.py`) and its own pacing, but one server means one setup and one set of
evidence rules for the model.

## Scraping Digitalarkivet, carefully

Digitalarkivet has no public API; Nasjonalarkivet said so in its forum in July
2025. Its classic pages are server-rendered HTML with stable class names and
English labels, and its new viewer serves standard IIIF Presentation 3
manifests and an IIIF Image API 3 service. The server reads those and nothing
else:

- **Only what a researcher asks for.** No tool walks the site. A search is one
  page of results; a book's pages are listed from its manifest, one request.
- **Five seconds between requests, at least.** The archive asks every crawler
  for that in `robots.txt`. The floor is not configurable downward.
- **A daily budget** (600 by default), kept on disk so a restart does not reset
  it. A research session that reads a whole confirmation list page by page
  uses about 60.
- **Parsed answers are cached**, not pages: the person-search page carries a
  500 KB filter form, and the cache keeps only the hits.
- **Stable identifiers.** Every scanned page has a permanent id (`kb…` or
  `ft…`) that Digitalarkivet itself publishes as a permalink
  (`goto.digitalarkivet.no/kb…`) and as a URN
  (`urn.digitalarkivet.no/URN:NBN:no-a1450-<id>.jpg`). Citations use those, so
  they outlive any change to the viewer.

`robots.txt` also disallows a list of named bots, AI agents among them. This
server is a researcher's tool acting on a researcher's request, at a pace the
archive sets for crawlers, and identifies itself in its User-Agent. The
archive publishes no terms of use; its reuse page allows free reuse of
unrestricted scans with credit. If Nasjonalarkivet publishes terms that say
otherwise, they win.

## Why the parsers read English pages

The `/en/` pages carry English labels ("Archive reference", "Serial no.") that
read the same across record types, which keeps the parser to one label set.
Values are passed through as written: a Norwegian occupation or farm name is
the record's text and is never translated.

## Sections are found, not assumed

A church book's lists (baptisms, confirmations, marriages…) are not marked in
the IIIF manifest. The source page links the first page of each list, so the
server finds each first page in the manifest and reports its image number. A
list usually runs until the next one begins, so `likely_last_image` is the
next start minus one; the word *likely* is deliberate.

## The National Library's access rules are the library's

Items marked `NORWAY` open only from Norwegian addresses. Search, snippets and
page numbers still work everywhere, and the server returns those with a note,
so a researcher can cite the page and read it in a library or apply for
Bokhylla access. It does not try another route to the image.

## Out of scope, by decision

- **Writing to any service, or logging in.** Digitalarkivet takes corrections
  from logged-in users; that is for a person to do.
- **Working around access rules or bot checks.** A challenge is reported as
  `blocked`; restricted records and Norway-only material are reported as such.
- **HBR (histreg.no).** Its search is a POST form, and its API is for partners.
- **Norway Heritage.** Its terms forbid duplication or redistribution without
  permission.
- **OCR or transcription of the scans.** The server hands back the image; the
  reading is the researcher's, or another tool's.
