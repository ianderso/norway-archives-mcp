# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

## [0.1.0] — 2026-10-11

First release.

### Added

- Six Digitalarkivet tools: `da_search_persons` (the advanced person search,
  by historical municipality and list type), `da_get_record` (a record's
  fields, the people in it, its source and its scanned page), `da_search_sources`
  (with each list's scanned and searchable flags), `da_get_source` (archive
  reference, image count and the image each list starts on, from the source
  page and the new viewer's IIIF manifest), `da_list_pages` and
  `da_download_page` (IIIF for church books and other `kb` pages, the URN
  resolver for census `ft` pages; one new file, never overwritten).
- Four National Library tools over its documented API: `nb_search`,
  `nb_search_inside` (printed page numbers even for Norway-only items),
  `nb_get_page` (ALTO OCR text where the item is open) and `nb_download_page`.
- `place_names` over Kartverket's place-name API, `municipalities` (the
  historical municipality numbers Digitalarkivet filters by, shipped with the
  package) and `cache_status`.
- A careful client: fixed hosts only, at least five seconds between
  Digitalarkivet requests and a daily budget kept across restarts, one second
  for the library and half a second for Kartverket, parsed answers cached on
  disk, one retry on 429/5xx, bounded answers, and an honest User-Agent.
- Every page answer carries a citation: source, archive reference, image
  number, permanent page id, permalink and URN image address.

[Unreleased]: https://github.com/ianderso/norway-archives-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ianderso/norway-archives-mcp/releases/tag/v0.1.0
