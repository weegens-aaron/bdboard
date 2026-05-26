"""Markdown rendering wrapper.

Tiny shim around markdown-it-py with the security knobs we want:
  - html=False         : raw <script> etc. in source markdown is escaped,
                         not passed through. Critical for any UI that ever
                         renders content the agent didn't author.
  - linkify=True       : bare URLs become clickable links automatically.
  - typographer=False  : we don't want smart-quote substitution mangling
                         code-adjacent prose (e.g. " becoming " inside
                         an inline `path/to/file`).

Returned strings should be marked Markup() at the template boundary so
Jinja doesn't double-escape the HTML we just produced.
"""

from __future__ import annotations

from functools import lru_cache

from markdown_it import MarkdownIt


@lru_cache(maxsize=1)
def _renderer() -> MarkdownIt:
    """Module-singleton renderer. lru_cache avoids re-constructing the
    MarkdownIt instance on every render — it's not free, and our config
    is process-static."""
    return MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": True,
            "typographer": False,
            "breaks": False,  # bd-flavored md uses real \n\n for breaks
        },
    )


def render(text: str | None) -> str:
    """Render markdown to HTML. Empty / None input returns empty string
    so templates can `{{ field | md }}` without guarding."""
    if not text:
        return ""
    return _renderer().render(text)
