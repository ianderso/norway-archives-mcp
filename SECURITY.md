# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's
[private vulnerability reporting](https://github.com/ianderso/norway-archives-mcp/security/advisories/new)
(the **Report a vulnerability** button on the repository's Security tab), not
in a public issue. Include what an attacker controls, what they gain, and the
steps to reproduce it.

You should hear back within a week. Fixes are released for the latest version
only.

## Scope

In scope: this server — the requests it makes, the files it writes (its cache
and the page images the two download tools save), and anything a tool
argument or a service's response can make it do.

Out of scope: Digitalarkivet, the National Library and Kartverket themselves,
which this project does not operate.

## The security model, briefly

- **No credentials.** None of the three services needs one. The server holds
  no key and sends none.
- **Tool arguments are treated as the attacker's.** A model writes them, and
  the model reads transcriptions, catalogue text and OCR that may carry
  injected instructions. Everything below is about what such an argument can
  make the server do.
- **Fixed hosts.** Requests go only to the three services' own hosts
  (`www`, `nye`, `goto` and `urn.digitalarkivet.no`; `api.nb.no` and
  `www.nb.no`; `api.kartverket.no`), over https. A request hook refuses any
  other host, including addresses read from a response, such as a manifest's
  image service or an ALTO link. `media.digitalarkivet.no` is allowed only as a
  redirect target whose address is read, never fetched.
- **Redirects are followed by hand,** and only within one service. A redirect
  anywhere else is reported to the caller and not followed.
- **Bounded answers.** A page or JSON answer over 8 MB or an image over 60 MB
  is refused as it streams in, whether or not its size was declared.
- **Read-only calls.** Every request is a GET. Nothing logs in, posts a form,
  or submits a correction.
- **Arguments are validated** — page ids, catalogue item ids, record
  addresses, municipality numbers against the shipped table — before they are
  placed in a request, and query parameters are percent-encoded.
- **Local writes.** The cache lives under `NORWAY_ARCHIVES_CACHE_DIR`, in files
  named by a hash of the request and written atomically; it holds parsed
  answers, not whole pages. The downloads write only the absolute path they
  are given, and only if that path, with its links resolved, ends in `.jpg` or
  `.jpeg`, has no hidden component, is not under `~/Library`, and lies inside
  `NORWAY_ARCHIVES_DOWNLOAD_DIR` when that is set (the operator's folder may
  itself be hidden or under `~/Library`; what a model adds below it may not).
  The bytes must be a JPEG by their first bytes. The file is created
  exclusively (an existing file or link is never overwritten or followed) and
  removed if writing fails; a refused download writes nothing at all.
- **Service responses carry untrusted text.** Transcriptions, catalogue
  entries and OCR reach the model verbatim, which makes them a channel for
  prompt injection. The server's instructions tell the model to treat that
  text as material, not as instructions, but the model still decides what to
  do next.
- **`NORWAY_ARCHIVES_CONTACT` is checked** for newlines and parentheses before
  it is placed in the User-Agent header.
