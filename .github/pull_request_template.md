<!-- What this changes and why. Link the issue it closes, if there is one. -->

## Checklist

What each item means is in [CONTRIBUTING.md](https://github.com/ianderso/norway-archives-mcp/blob/main/CONTRIBUTING.md#what-a-change-carries).

- [ ] A test that fails without this change.
- [ ] `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` pass.
- [ ] Tool descriptions are written for the model and fit under `DESCRIPTION_BUDGET`. Raising it takes a pull request of its own, saying why.
- [ ] Anything returning transcript or OCR text says it is a lead, not the record.
- [ ] Every result that names a scanned page carries its citation (source, archive reference, image, permanent id).
- [ ] Failures come back as an `error` result, not an exception.
- [ ] If a tool or parameter changed: `tests/fixtures/tool_schema.json` is regenerated and the README tables are updated.
- [ ] If this relies on how a site answers: a recorded fixture, and what was observed and when in `docs/API-NOTES.md`.
- [ ] If `data/digitalarkivet_codes.json` changed: re-read from the live search form, and the date noted in `docs/API-NOTES.md`.
- [ ] A `CHANGELOG.md` entry, if users will notice the change.
- [ ] Nothing here writes to a service, logs in, goes faster than the services ask, or works around a bot check or an access rule.
