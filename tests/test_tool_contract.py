"""Contract tests over the registered MCP tool surface.

These assert properties of the tools *as a client sees them*: their names,
their JSON schema, their annotations, and the size of the description block
shipped on every session. The rest of the suite exercises the client and the
parsers, which means a ``Field`` typo or a dropped docstring could change the
published contract without failing a single test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from norway_archives_mcp import server
from norway_archives_mcp.server import mcp

SNAPSHOT = Path(__file__).parent / "fixtures" / "tool_schema.json"
README = Path(__file__).parent.parent / "README.md"

#: Ceiling on the combined tool descriptions, which are sent to the model on
#: every session before any work happens. Raise it deliberately, not by accident.
#: 0.1.0 ships about 2,500 characters.
DESCRIPTION_BUDGET = 3_000

#: Tools that touch no network at all.
LOCAL_TOOLS = {"municipalities", "cache_status"}

#: The tools that write anything, and only a new local file.
WRITES_LOCAL_FILE = {"da_download_page", "nb_download_page"}

#: Words that would mean a tool changes something somewhere.
WRITE_WORDS = re.compile(r"(^|_)(insert|update|edit|publish|delete|merge|add|create|write)(_|$)")


async def _tools() -> list:
    return sorted(await mcp.list_tools(), key=lambda t: t.name)


def _params(tool) -> dict:
    return (tool.input_schema or {}).get("properties", {}) or {}


async def test_every_tool_has_a_description():
    assert [t.name for t in await _tools() if not (t.description or "").strip()] == []


async def test_every_parameter_has_a_description():
    undocumented = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name, spec in _params(t).items()
        if not (spec.get("description") or "").strip()
    ]
    assert undocumented == []


async def test_no_parameter_leaks_a_python_repr():
    leaked = [
        t.name
        for t in await _tools()
        if "FieldInfo" in json.dumps(t.input_schema)
        or "PydanticUndefined" in json.dumps(t.input_schema)
    ]
    assert leaked == []


async def test_tool_names_and_parameters_match_the_snapshot():
    """Renaming a tool or a parameter breaks callers; make it a visible diff.

    Regenerate deliberately with ``uv run python -m tests.regen_tool_snapshot``.
    """
    current = {t.name: sorted(_params(t)) for t in await _tools()}
    assert current == json.loads(SNAPSHOT.read_text())


async def test_every_tool_appears_in_the_readme_and_the_count_is_right():
    doc = README.read_text()
    names = {t.name for t in await _tools()}
    documented = set(re.findall(r"\| `([a-z_]+)`", doc))
    assert names <= documented, f"not in the README: {sorted(names - documented)}"
    assert documented - names == set(), (
        f"README documents removed tools: {sorted(documented - names)}"
    )
    words = {13: "thirteen"}
    assert f"publishes {words.get(len(names), len(names))} tools" in doc


async def test_description_block_stays_within_budget():
    total = sum(len(t.description or "") for t in await _tools())
    assert total <= DESCRIPTION_BUDGET, f"descriptions total {total}, over {DESCRIPTION_BUDGET}"


async def test_descriptions_ship_without_indentation_on_every_python():
    """Python 3.13 dedents docstrings and 3.11 and 3.12 do not; the budget counts what is sent."""
    indented = [
        t.name
        for t in await _tools()
        if any(line.startswith(" ") for line in (t.description or "").splitlines())
    ]
    assert indented == []


async def test_required_parameters_have_no_default():
    wrong = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name in (t.input_schema or {}).get("required", [])
        if "default" in _params(t)[name]
    ]
    assert wrong == []


async def test_annotations_tell_the_truth():
    for tool in await _tools():
        hints = tool.annotations
        assert hints is not None, tool.name
        if tool.name in WRITES_LOCAL_FILE:
            assert hints.read_only_hint is False and hints.destructive_hint is False
        else:
            assert hints.read_only_hint is True, tool.name
        assert hints.open_world_hint is (tool.name not in LOCAL_TOOLS), tool.name


async def test_no_tool_name_promises_a_write():
    assert [t.name for t in await _tools() if WRITE_WORDS.search(t.name)] == []


async def test_every_schema_refuses_unknown_parameters():
    assert all((t.input_schema or {}).get("additionalProperties") is False for t in await _tools())


def test_schema_housekeeping_ran_at_import():
    assert server.SCHEMA_CHARS_SAVED >= 0
    assert server.TOOLS_REFUSING_UNKNOWN == 13
