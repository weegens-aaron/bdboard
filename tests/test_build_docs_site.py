"""Tests for the static HTML doc-site builder (tools/build_docs_site.py).

These lock the *fidelity contract* of the flowdoc-html portable build: GitHub
callouts, mermaid fences, heading-anchor slugs, and the relative-link rewrite
rules (.md -> .html, working-file -> index, in-repo source -> GitHub blob/tree).
The builder is a standalone script under tools/ (not part of the bdboard
package), so we load it by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "tools" / "build_docs_site.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_docs_site", _MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass introspection needs this registered
    spec.loader.exec_module(mod)
    return mod


builder = _load_builder()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Key Flows", "key-flows"),
        ("API Surface", "api-surface"),
        ("Views & Pages", "views--pages"),
        ("  Trailing/Leading!  ", "trailingleading"),
    ],
)
def test_slugify_matches_github_style(text, expected):
    assert builder.slugify(text) == expected


def test_extract_callouts_pulls_blockquote_and_leaves_placeholder():
    md = "Intro.\n\n> [!WARNING]\n> Be careful here.\n> Second line.\n\nOutro."
    stripped, callouts = builder.extract_callouts(md)
    assert len(callouts) == 1
    ctype, body = callouts[0]
    assert ctype == "WARNING"
    assert "Be careful here." in body
    assert "Second line." in body
    assert builder._PLACEHOLDER.format(0) in stripped
    assert "[!WARNING]" not in stripped


def test_render_callout_emits_styled_div():
    md = builder.make_renderer()
    html = builder.render_callout("NOTE", "Hello **world**.", md)
    assert 'class="callout callout-note"' in html
    assert "callout-title" in html
    assert "<strong>world</strong>" in html


def test_mermaid_fence_becomes_mermaid_pre_not_code_block():
    md = builder.make_renderer()
    out = md.render("```mermaid\ngraph TD\nA-->B\n```", {})
    assert '<pre class="mermaid">' in out
    assert 'class="language-mermaid"' not in out
    # arrow content survives (escaped) so mermaid.js can read it back
    assert "A--&gt;B" in out


def test_headings_get_github_style_id_anchors():
    md = builder.make_renderer()
    out = md.render("# Top\n\n## Key Flows\n\n## Key Flows\n", {})
    assert '<h2 id="key-flows">' in out
    # duplicate slug is de-duped like GitHub
    assert '<h2 id="key-flows-1">' in out


def test_rewrite_links_md_to_html():
    out = builder.rewrite_links('<a href="Concepts/DeriveLayer.md">x</a>', "", Path("__docs"))
    assert 'href="Concepts/DeriveLayer.html"' in out


def test_rewrite_links_working_file_points_to_root_index():
    out = builder.rewrite_links('<a href="../_Manifest.md">m</a>', "../", Path("__docs/Endpoints"))
    assert 'href="../index.html"' in out


def test_rewrite_links_preserves_anchor_fragment():
    out = builder.rewrite_links(
        '<a href="../Architecture.md#key-flows">x</a>', "../", Path("__docs/Flows")
    )
    assert 'href="../Architecture.html#key-flows"' in out


def test_rewrite_links_source_file_becomes_github_blob():
    # __docs/Architecture.md links to ../src/bdboard/app.py (a real repo file)
    out = builder.rewrite_links('<a href="../src/bdboard/app.py">app</a>', "", Path("__docs"))
    assert f"{builder.GITHUB_BASE}/blob/{builder.GITHUB_REF}/src/bdboard/app.py" in out


def test_rewrite_links_external_untouched():
    href = '<a href="https://example.com/x">e</a>'
    assert builder.rewrite_links(href, "", Path("__docs")) == href


def test_verify_on_real_built_site_is_clean():
    """The repo ships a built site under docs/; the VERIFY gate must pass on it
    (source<->output parity, links resolve, no raw fences/callouts, no leaks)."""
    targets = builder.resolve_targets("both")
    if not all(s.out.exists() for s in targets):
        pytest.skip("doc site not built; run `make docs-site`")
    assert builder.verify(targets) == []
