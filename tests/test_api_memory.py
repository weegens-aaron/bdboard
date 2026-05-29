"""Route tests for GET /api/memory (the memory list region partial).

We invoke the endpoint coroutine directly with a minimal ASGI Request
(no TestClient / httpx dependency needed) and assert on the rendered
HTML. bd.memories is stubbed so no real subprocess is spawned.

Covers the cases called out in
docs/design/bdboard-5p1/memory-view-design.md §5/§6 (bead B):
  - full list lists all memories, count + cards rendered
  - search renders the "matching" count copy + forwards q server-side
  - no-memories-at-all empty state
  - no-match-for-query empty state (mirrors CLI copy)
  - body rendered through the shared `md` markdown filter
  - key rendered as a monospace h3 heading
  - result count lives in an aria-live=polite region
  - bd failure degrades gracefully instead of 500-ing the swap
"""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module


def _request(query_string: str = "") -> Request:
    """Build a minimal GET Request for the /api/memory route."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/memory",
        "query_string": query_string.encode(),
        "headers": [],
    }
    return Request(scope)


def _stub_memories(result: Any) -> list[str | None]:
    """Replace bd.memories with a stub that records the query it received
    and returns ``result`` (or raises it if it's an Exception)."""
    seen: list[str | None] = []

    async def fake_memories(query: str | None = None) -> Any:
        seen.append(query)
        if isinstance(result, Exception):
            raise result
        return result

    app_module.bd.memories = fake_memories  # type: ignore[assignment]
    return seen


def _call(query_string: str = "", q: str = "") -> tuple[int, str]:
    """Invoke api_memory and return (status_code, decoded body)."""
    resp = asyncio.run(app_module.api_memory(_request(query_string), q=q))
    return resp.status_code, resp.body.decode()


def test_full_list_renders_count_and_cards() -> None:
    _stub_memories(
        [
            {"key": "alpha", "body": "first body"},
            {"key": "bravo", "body": "second body"},
        ]
    )

    status, body = _call()

    assert status == 200
    assert "2 memories" in body
    assert "alpha" in body
    assert "bravo" in body
    # Keys render as monospace h3 headings.
    assert '<h3 class="memory-key">alpha</h3>' in body
    # Result count is in an aria-live=polite region.
    assert 'aria-live="polite"' in body


def test_singular_count_copy() -> None:
    _stub_memories([{"key": "solo", "body": "only one"}])

    _, body = _call()

    assert "1 memory" in body
    assert "1 memories" not in body


def test_search_passes_query_and_renders_matching_copy() -> None:
    seen = _stub_memories([{"key": "bd-edit-stalls", "body": "never run bd edit"}])

    status, body = _call(query_string="q=edit", q="edit")

    assert status == 200
    # Server-side search: q is forwarded to bd.memories.
    assert seen == ["edit"]
    assert "1 matching" in body
    assert "edit" in body


def test_no_memories_at_all_empty_state() -> None:
    _stub_memories([])

    status, body = _call()

    assert status == 200
    assert "No memories yet" in body
    assert "bd remember" in body


def test_no_match_for_query_empty_state_mirrors_cli() -> None:
    _stub_memories([])

    status, body = _call(query_string="q=nope", q="nope")

    assert status == 200
    # Mirrors the CLI copy: No memories matching "<q>"
    assert "No memories matching" in body
    assert "nope" in body


def test_body_rendered_through_markdown_filter() -> None:
    _stub_memories([{"key": "md-test", "body": "run `bd remember` and **save**"}])

    _, body = _call()

    # Markdown filter turns backticks into <code> and ** into <strong>.
    assert "<code>bd remember</code>" in body
    assert "<strong>save</strong>" in body


def test_bd_failure_degrades_gracefully() -> None:
    _stub_memories(RuntimeError("bd exploded"))

    status, body = _call()

    # Partial swap must not 500 — degrade to a friendly inline message.
    assert status == 200
    assert "Couldn" in body
    assert 'aria-live="polite"' in body


def test_whitespace_query_is_treated_as_list_all() -> None:
    seen = _stub_memories([])

    _, body = _call(query_string="q=%20%20%20", q="   ")

    # Whitespace-only query collapses to the list-all path (count copy,
    # not "matching"), and the stripped term is forwarded.
    assert seen == [""]
    assert "matching" not in body


def test_edit_button_escapes_special_chars_in_body() -> None:
    """Regression test: edit button must work with quotes/newlines in body.

    bdboard-eee: The edit button broke when the body contained double quotes
    because tojson output wasn't HTML-escaped for the onclick attribute.
    Fix: use data attributes with | e filter, read via dataset in JS.
    """
    _stub_memories(
        [
            {
                "key": "tricky",
                "body": "Use \"double quotes\" and 'single' too",
            },
        ]
    )

    status, body = _call()

    assert status == 200
    # The data-body attribute must be properly HTML-escaped.
    # Double quotes become &quot;, preventing attribute breakout.
    assert 'data-body="' in body
    assert "&quot;double quotes&quot;" in body
    # onclick reads from dataset, not inline template vars.
    assert "editMemory(this.dataset.key, this.dataset.body)" in body
