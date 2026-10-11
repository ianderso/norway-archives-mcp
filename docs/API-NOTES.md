# API notes

What each service was observed to do, and when. Recorded 2026-10-10 and
2026-10-11 from a US address, without signing in. The fixtures in
`tests/fixtures/` come from these observations.

## Digitalarkivet (www.digitalarkivet.no, nye.digitalarkivet.no)

No documented API. Every address below answers a plain GET.

| What | Address | Answer |
| --- | --- | --- |
| Person search | `/en/search/persons/advanced?lastname=…&firstname=…&m[]=<municipality>&lt[]=<list type>&event_year_from=…&event_year_to=…&birth_year_from=…&birth_year_to=…&birth_place=…&domicile=…&no_alias=1&page=N` | HTML. `[data-hits]` holds the total; `#searchResultList div.unit` one hit each (`.name a` record, `.born`, `.gender .sr-only`, `.place`, `.action` event date, `.stilling-stand`, `.role`, `.source a`). 50 hits a page. `*` is a wildcard in names. |
| Record | `/en/view/<db>/<id>` (church books, emigrants…) or `/en/census/person/<id>` | HTML. `#permanentId`; label/value pairs as a label cell followed by a `.ssp-semibold` value cell; `div.panel` for the event and the people (`.data-item`); `div.card` for source information and contributors; `ul.da-breadcrumb`. The scanned page links as `goto.digitalarkivet.no/kb…` (church books) or `media.digitalarkivet.no/ft…` (censuses). |
| Source search | `/en/search/sources?s=…&from=…&to=…&m[]=…&lt[]=…&page=N` | HTML. Each `div.unit` carries `.name a` (`/en/source/<id>`), `.archive`, and `.lists .unit-list` rows: `<strong>` label, years, a `current_list_type=<code>` browse link when scanned, and a `/search/` link when searchable ("Not searchable" otherwise). |
| Source | `/en/source/<id>` | HTML. "Archive reference", "Source ID" and the rest as label/value pairs; one `nye.digitalarkivet.no/source/<id>/parish/<uuid>?current_list_type=<code>` link per list, pointing at its first page. |
| IIIF manifest | `https://nye.digitalarkivet.no/api/media-file/image/presentation/manifest/<source id>.json` | IIIF Presentation 3. One canvas per image, in order; the canvas id ends in the page's uuid; the painting annotation carries `metadata` with the file name (`kb….jp2`), `body.service[0].id` (an Image API 3 service, level 2) and `isRestricted`. No `structures`. A 500-image book's manifest is about 750 KB. Censuses (`ft…` pages) have none: 404. |
| Image | `<service>/full/!<w>,<h>/0/default.jpg` | JPEG. Full size about 5,000 × 3,900 for a church-book spread. |
| Permalink, `kb` | `https://goto.digitalarkivet.no/kb…` | 303 to `nye.digitalarkivet.no/source/<id>/parish/<uuid>`. An unknown id does not redirect. |
| Permalink, `ft` | `https://www.digitalarkivet.no/en/ft…` | 302 to `media.digitalarkivet.no/view/<source id>/<image>`. (`goto` answers 404 for `ft` ids.) |
| URN image | `https://urn.digitalarkivet.no/URN:NBN:no-a1450-<page id>.jpg` | Full-size JPEG, for `kb` and `ft` ids alike (3.5 MB for a census page). |

**Codes.** Municipality numbers (`m[]`) and list types (`lt[]`) are the
values of the person-search form's checkboxes, read into
`data/digitalarkivet_codes.json` on 2026-10-11: 858 historical municipalities
under 34 old counties, and 34 list types (`dp` born and baptised, `kf`
confirmation, `vi` married, `gr` deceased and buried, `if` in-migrated, `uf`
out-migrated, `fl` in- and out-migrated…).

**Terms.** No terms-of-use page; the footer links privacy and accessibility
only. The reuse page (`/content/1570`) allows free reuse of unrestricted scans
in print and online, crediting the holding archive. `robots.txt`: about 140
named bots (AI agents among them) `Disallow: /`; everyone else `Crawl-delay: 5`.
Nasjonalarkivet's forum, July 2025: no API services beyond the existing ones.

## Nasjonalbiblioteket (api.nb.no, www.nb.no)

Documented at <https://api.nb.no>. No key.

| What | Address | Answer |
| --- | --- | --- |
| Search | `/catalog/v1/items?q=…&searchType=FULL_TEXT_SEARCH&filter=mediatype:bøker&filter=year:[1800 TO 1900]&digitalAccessibleOnly=true&size=20&page=0` | JSON: `page.totalElements`, `_embedded.items[]` with `id`, `metadata` (title, creators, originInfo.issued, mediaTypes, subject) and `accessInfo` (`accessAllowedFrom` EVERYWHERE / NORWAY / NB, `isPublicDomain`, `isDigital`, `viewability`). `filter=date:[YYYYMMDD TO YYYYMMDD]` works too. |
| One item | `/catalog/v1/items/<id>` | As a search hit, but authors are under `metadata.people[]` (name, roles), not `creators`. |
| Search inside | `/catalog/v1/items/<id>/contentfragments?q=…&fragSize=200&fragments=N` | `contentFragments[]`: `pageNumber` (the printed number), `pageid` (a URN), `text` with `<em>` around the match. Works for NORWAY items from abroad; the snippet is then only the word. |
| Manifest | `/catalog/v1/iiif/<id>/manifest` | IIIF Presentation 2. Canvas `@id` ends in the page URN, `label` is the printed page number (`-` for unnumbered), `@seeAlso` the ALTO address. Answers for NORWAY items from abroad too. |
| Page text | `/catalog/v1/metadata/<id>/altos/<page URN>` | ALTO 3 XML (Tesseract). 401 for NORWAY items from abroad. |
| Image | `https://www.nb.no/services/image/resolver/<page URN>/full/!<w>,<h>/0/native.jpg` | IIIF Image API 2. 403 for NORWAY items from abroad. |

## Kartverket (api.kartverket.no)

`/stedsnavn/v1/navn?sok=…&fuzzy=true&knr=<municipality number>&kommunenavn=…&fnr=…&fylkesnavn=…&utkoordsys=4258&treffPerSide=N&side=1`.
OpenAPI at `/stedsnavn/v1/openapi.json`. JSON: `metadata.totaltAntallTreff`,
`navn[]` with `skrivemåte`, `navneobjekttype` (Gard, Bruk, Tettsted, Elv…),
`stedsnummer`, `kommuner[]`, `fylker[]`, `representasjonspunkt` (`nord`, `øst`
in EPSG:4258). `*` is a wildcard. Municipalities are today's: the 2020 mergers
apply. No login or authorisation.
