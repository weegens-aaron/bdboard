#!/usr/bin/env python3
"""Build the static HTML documentation site(s) from the FlowDoc markdown.

This is the *portable build contract* fallback (STEP 3) of the ``flowdoc-html``
formula: the ``md-to-html`` skill is preferred, but when it is not vendored in
the repo this script reproduces the skill's output shape with a generic
markdown toolchain (``markdown-it-py``, already a project dependency).

It converts::

    __docs/*.md  ->  docs/maintainer/*.html   (mirrors the directory tree)
    _docs/*.md   ->  docs/user/*.html

and honours the build contract:

* fenced ``mermaid`` blocks render client-side via mermaid.js (no raw fences);
* GitHub callouts (``> [!NOTE]`` ...) become styled callout boxes;
* every doc directory keeps its ``index.html`` navigation page;
* a single shared ``docs/style.css`` is linked by every page;
* in-repo ``.md`` links are rewritten to the matching ``.html``;
* a top-level ``docs/index.html`` landing page links the built site(s).

Working files (any ``_*.md`` such as ``_Manifest.md`` / ``_FlowDocGuide.md``)
are NOT published; links to them are rewritten to the site's root index page,
which is the human-facing catalog.

Usage::

    python tools/build_docs_site.py [--target both|maintainer|user] [--check]

``--check`` runs the VERIFY gate only (no rebuild) and exits non-zero on any
contract violation. A normal build runs the gate after writing and exits
non-zero if it fails.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent
DOCS_OUT = ROOT / "docs"

CALLOUT_TYPES = ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION")


@dataclass(frozen=True)
class Site:
    key: str
    src: Path
    out: Path
    label: str
    blurb: str


SITES: dict[str, Site] = {
    "maintainer": Site(
        key="maintainer",
        src=ROOT / "__docs",
        out=DOCS_OUT / "maintainer",
        label="Maintainer Docs",
        blurb="Developer-facing architecture, flows, endpoints and concepts.",
    ),
    "user": Site(
        key="user",
        src=ROOT / "_docs",
        out=DOCS_OUT / "user",
        label="User Guide",
        blurb="Task-focused guides, tutorials and reference for using bdboard.",
    ),
}


# --------------------------------------------------------------------------- #
# Markdown renderer (build-time; distinct from the in-app security shim md.py) #
# --------------------------------------------------------------------------- #
def _render_fence(tokens, idx, options, env):  # noqa: ANN001 - md-it API
    """Fence renderer: mermaid -> ``<pre class="mermaid">`` so mermaid.js can
    pick it up; everything else -> a normal escaped code block."""
    tok = tokens[idx]
    info = (tok.info or "").strip()
    lang = info.split()[0] if info else ""
    content = html.escape(tok.content)
    if lang == "mermaid":
        return f'<pre class="mermaid">{content}</pre>\n'
    cls = f' class="language-{html.escape(lang)}"' if lang else ""
    return f"<pre><code{cls}>{content}</code></pre>\n"


_SLUG_STRIP_RE = re.compile(r"[^\w\- ]+")


def slugify(text: str) -> str:
    """GitHub-style heading slug: lowercase, drop punctuation, spaces->hyphens."""
    slug = _SLUG_STRIP_RE.sub("", text.strip().lower())
    return slug.replace(" ", "-")


def _render_heading_open(tokens, idx, options, env):  # noqa: ANN001 - md-it API
    """Emit GitHub-style ``id`` anchors on headings so in-page ``#fragment``
    links resolve. De-dupes repeated slugs the way GitHub does (``-1``, ``-2``)."""
    tok = tokens[idx]
    inline = tokens[idx + 1]
    base = slugify(inline.content) if inline and inline.content else ""
    seen = env.setdefault("_slugs", {})
    slug = base
    if base in seen:
        seen[base] += 1
        slug = f"{base}-{seen[base]}"
    else:
        seen[base] = 0
    return f'<{tok.tag} id="{html.escape(slug, quote=True)}">'


def make_renderer() -> MarkdownIt:
    md = MarkdownIt(
        "commonmark",
        {"html": False, "linkify": False, "typographer": False, "breaks": False},
    ).enable("table")
    md.renderer.rules["fence"] = _render_fence
    md.renderer.rules["heading_open"] = _render_heading_open
    return md


# --------------------------------------------------------------------------- #
# Callout extraction                                                          #
# --------------------------------------------------------------------------- #
_CALLOUT_RE = re.compile(r"^>\s*\[!(" + "|".join(CALLOUT_TYPES) + r")\]\s*(.*)$")
_PLACEHOLDER = "%%%BDBOARD_CALLOUT_{}%%%"


def extract_callouts(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Pull GitHub callout blockquotes out of the markdown, leaving a unique
    placeholder paragraph in their place. Returns (text, [(type, body_md)])."""
    lines = text.split("\n")
    out: list[str] = []
    callouts: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        m = _CALLOUT_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        ctype = m.group(1)
        body: list[str] = []
        if m.group(2).strip():
            body.append(m.group(2))
        i += 1
        while i < len(lines) and lines[i].lstrip().startswith(">"):
            body.append(re.sub(r"^\s*>\s?", "", lines[i]))
            i += 1
        out.extend(["", _PLACEHOLDER.format(len(callouts)), ""])
        callouts.append((ctype, "\n".join(body)))
    return "\n".join(out), callouts


def render_callout(ctype: str, body_md: str, md: MarkdownIt) -> str:
    inner = md.render(body_md).strip()
    label = ctype.capitalize()
    return (
        f'<div class="callout callout-{ctype.lower()}">'
        f'<p class="callout-title">{label}</p>\n{inner}\n</div>'
    )


# --------------------------------------------------------------------------- #
# Link rewriting                                                              #
# --------------------------------------------------------------------------- #
_HREF_RE = re.compile(r'href="([^"]+)"')
GITHUB_BASE = "https://github.com/weegens-aaron/bdboard"
GITHUB_REF = "main"


def rewrite_links(html_str: str, root_prefix: str, src_md_dir: Path) -> str:
    """Rewrite relative ``.md`` links to ``.html``; links to ``_*`` working
    files become the site-root ``index.html`` (``root_prefix`` is the relative
    path from this page up to the site root, e.g. ``../`` or ``""``)."""

    def repl(m: re.Match[str]) -> str:
        href = m.group(1)
        if re.match(r"^(https?:|mailto:|tel:|#|/|data:)", href):
            return m.group(0)
        path, sep, anchor = href.partition("#")
        base = path.rsplit("/", 1)[-1]
        if base.startswith("_") and base.endswith(".md"):
            new = f"{root_prefix}index.html"
        elif path.endswith(".md"):
            new = path[:-3] + ".html"
        else:
            # Non-doc relative link: resolve against the markdown source dir.
            # If it points at a real in-repo file/dir, link to it on GitHub.
            resolved = (ROOT / src_md_dir / path).resolve()
            try:
                repo_rel = resolved.relative_to(ROOT)
            except ValueError:
                return m.group(0)
            if not resolved.exists():
                return m.group(0)
            kind = "tree" if resolved.is_dir() else "blob"
            return f'href="{GITHUB_BASE}/{kind}/{GITHUB_REF}/{repo_rel.as_posix()}"'
        if sep:
            new = f"{new}#{anchor}"
        return f'href="{new}"'

    return _HREF_RE.sub(repl, html_str)


# --------------------------------------------------------------------------- #
# Page assembly                                                               #
# --------------------------------------------------------------------------- #
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def doc_title(text: str, fallback: str) -> str:
    m = _TITLE_RE.search(text)
    return m.group(1).strip() if m else fallback


def page_template(*, title: str, body: str, nav: str, css_href: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{css_href}">
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">{nav}</header>
<main id="main" class="content">
{body}
</main>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({{ startOnLoad: true, securityLevel: "strict" }});
</script>
</body>
</html>
"""


def build_nav(site: Site, root_prefix: str, landing_prefix: str) -> str:
    others = [s for s in SITES.values() if s.key != site.key]
    links = [
        f'<a href="{landing_prefix}index.html">Docs Home</a>',
        f'<a href="{root_prefix}index.html">{html.escape(site.label)}</a>',
    ]
    for o in others:
        # other edition lives at ../../<key>/index.html relative to this page
        links.append(f'<a href="{landing_prefix}{o.key}/index.html">{html.escape(o.label)}</a>')
    return (
        f'<span class="site-title">bdboard &middot; {html.escape(site.label)}</span>'
        f'<nav class="site-nav">{" ".join(links)}</nav>'
    )


def render_markdown_page(text: str, md: MarkdownIt, root_prefix: str, src_md_dir: Path) -> str:
    stripped, callouts = extract_callouts(text)
    body = md.render(stripped, {})
    for n, (ctype, body_md) in enumerate(callouts):
        body = body.replace(f"<p>{_PLACEHOLDER.format(n)}</p>", render_callout(ctype, body_md, md))
    return rewrite_links(body, root_prefix, src_md_dir)


# --------------------------------------------------------------------------- #
# Site build                                                                  #
# --------------------------------------------------------------------------- #
def iter_md(src: Path):
    for path in sorted(src.rglob("*.md")):
        if path.name.startswith("_"):
            continue  # working files (_Manifest, _FlowDocGuide, ...) never publish
        yield path


def build_site(site: Site, md: MarkdownIt) -> int:
    if site.out.exists():
        shutil.rmtree(site.out)
    site.out.mkdir(parents=True, exist_ok=True)
    count = 0
    for src_path in iter_md(site.src):
        rel = src_path.relative_to(site.src)
        depth = len(rel.parts) - 1
        root_prefix = "../" * depth
        landing_prefix = "../" * (depth + 1)  # up to docs/
        text = src_path.read_text(encoding="utf-8")
        title = doc_title(text, rel.stem)
        src_md_dir = src_path.parent.relative_to(ROOT)
        body = render_markdown_page(text, md, root_prefix, src_md_dir)
        nav = build_nav(site, root_prefix, landing_prefix)
        css_href = f"{landing_prefix}style.css"
        out_path = site.out / rel.with_suffix(".html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            page_template(title=title, body=body, nav=nav, css_href=css_href),
            encoding="utf-8",
        )
        count += 1
    return count


def build_landing(targets: list[Site]) -> None:
    cards = []
    for s in targets:
        cards.append(
            f'<a class="card" href="{s.key}/index.html">'
            f"<h2>{html.escape(s.label)}</h2>"
            f"<p>{html.escape(s.blurb)}</p></a>"
        )
    body = (
        "<h1>bdboard Documentation</h1>\n"
        "<p>Static documentation site for <strong>bdboard</strong> — a "
        "single-binary, read-mostly web dashboard for <code>bd</code> (beads) "
        "workspaces.</p>\n"
        f'<div class="card-grid">{"".join(cards)}</div>'
    )
    nav = '<span class="site-title">bdboard Documentation</span><nav class="site-nav"></nav>'
    DOCS_OUT.mkdir(parents=True, exist_ok=True)
    (DOCS_OUT / "index.html").write_text(
        page_template(title="bdboard Documentation", body=body, nav=nav, css_href="style.css"),
        encoding="utf-8",
    )


STYLE_CSS = """/* bdboard docs site — shared stylesheet.
   Palette: Walmart blue.100 accent; WCAG 2.2 AA contrast (>= 4.5:1 text). */
:root {
  --blue: #0053e2;
  --blue-dark: #002a8a;
  --ink: #16191f;          /* body text on white: ~15:1 */
  --muted: #4a4f57;        /* secondary text on white: ~8:1 */
  --bg: #ffffff;
  --subtle: #f4f6f8;
  --border: #d3d6da;
  --code-bg: #f4f6f8;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  color: var(--ink);
  background: var(--bg);
  line-height: 1.6;
}
.skip-link {
  position: absolute; left: -999px; top: 0; background: var(--blue);
  color: #fff; padding: .5rem 1rem; z-index: 100;
}
.skip-link:focus { left: 0; }
.site-header {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 1rem;
  padding: .85rem 1.5rem; background: var(--blue); color: #fff;
}
.site-title { font-weight: 700; }
.site-nav { display: flex; flex-wrap: wrap; gap: 1.1rem; }
.site-nav a, .site-header a { color: #fff; text-decoration: none; font-weight: 600; }
.site-nav a:hover, .site-nav a:focus { text-decoration: underline; }
.content {
  max-width: 52rem; margin: 0 auto; padding: 2rem 1.5rem 5rem;
}
.content h1 { font-size: 2rem; line-height: 1.2; margin-top: 0; }
.content h2 { margin-top: 2.2rem; border-bottom: 1px solid var(--border);
  padding-bottom: .25rem; }
.content a { color: var(--blue-dark); }
.content a:hover { color: var(--blue); }
code {
  background: var(--code-bg); padding: .12em .35em; border-radius: 4px;
  font-size: .92em; font-family: "SFMono-Regular", Menlo, Consolas, monospace;
}
pre {
  background: var(--code-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 1rem; overflow-x: auto;
}
pre code { background: none; padding: 0; }
pre.mermaid { background: var(--bg); border: none; text-align: center; }
table { border-collapse: collapse; width: 100%; margin: 1.2rem 0; }
th, td { border: 1px solid var(--border); padding: .5rem .7rem; text-align: left; }
th { background: var(--subtle); }
blockquote {
  margin: 1.2rem 0; padding: .4rem 1rem; border-left: 4px solid var(--border);
  color: var(--muted);
}
/* Callouts — colors chosen for >= 4.5:1 title text on their tinted bg. */
.callout { margin: 1.2rem 0; padding: .8rem 1rem; border-radius: 8px;
  border: 1px solid; border-left-width: 5px; }
.callout-title { margin: 0 0 .4rem; font-weight: 700; }
.callout > :last-child { margin-bottom: 0; }
.callout-note { background: #eef3ff; border-color: #0053e2; }
.callout-note .callout-title { color: #002a8a; }
.callout-tip { background: #eaf6e6; border-color: #2a8703; }
.callout-tip .callout-title { color: #1c5c02; }
.callout-important { background: #f1ecff; border-color: #5a3ec8; }
.callout-important .callout-title { color: #3a248a; }
.callout-warning { background: #fff6e6; border-color: #995213; }
.callout-warning .callout-title { color: #7a4110; }
.callout-caution { background: #fdecea; border-color: #ea1100; }
.callout-caution .callout-title { color: #a60c00; }
.card-grid { display: grid; gap: 1.2rem; grid-template-columns:
  repeat(auto-fit, minmax(15rem, 1fr)); margin-top: 1.5rem; }
.card { display: block; padding: 1.2rem 1.4rem; border: 1px solid var(--border);
  border-radius: 10px; text-decoration: none; color: var(--ink);
  background: var(--subtle); }
.card:hover, .card:focus { border-color: var(--blue); }
.card h2 { margin: 0 0 .4rem; color: var(--blue-dark); border: none; }
.card p { margin: 0; color: var(--muted); }
"""


def write_style() -> None:
    DOCS_OUT.mkdir(parents=True, exist_ok=True)
    (DOCS_OUT / "style.css").write_text(STYLE_CSS, encoding="utf-8")


# --------------------------------------------------------------------------- #
# VERIFY gate                                                                 #
# --------------------------------------------------------------------------- #
def verify(targets: list[Site]) -> list[str]:
    problems: list[str] = []
    for site in targets:
        if not site.out.exists():
            problems.append(f"{site.key}: output dir missing ({site.out})")
            continue
        srcs = {p.relative_to(site.src).with_suffix(".html") for p in iter_md(site.src)}
        outs = {p.relative_to(site.out) for p in site.out.rglob("*.html")}
        for missing in sorted(srcs - outs):
            problems.append(f"{site.key}: missing HTML output for {missing}")
        for extra in sorted(outs - srcs):
            problems.append(f"{site.key}: unexpected HTML output {extra}")
        # leaked working files
        for leaked in site.out.rglob("_*.html"):
            problems.append(f"{site.key}: working file leaked into site: {leaked.name}")

    # content + link checks across the whole built tree
    pages = [DOCS_OUT / "index.html"]
    for site in targets:
        pages.extend(site.out.rglob("*.html"))
    for page in pages:
        if not page.exists():
            continue
        txt = page.read_text(encoding="utf-8")
        if 'class="language-mermaid"' in txt:
            problems.append(f"{page}: raw mermaid code block (not rendered)")
        if re.search(r"\[!(?:" + "|".join(CALLOUT_TYPES) + r")\]", txt):
            problems.append(f"{page}: literal callout marker not rendered")
        for href in _HREF_RE.findall(txt):
            if re.match(r"^(https?:|mailto:|tel:|#|/|data:)", href):
                continue
            target = (page.parent / href.split("#", 1)[0]).resolve()
            if not target.exists():
                problems.append(f"{page}: broken link -> {href}")
    return problems


# ------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def resolve_targets(target: str) -> list[Site]:
    if target == "both":
        return [SITES["maintainer"], SITES["user"]]
    return [SITES[target]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["both", "maintainer", "user"], default="both")
    ap.add_argument("--check", action="store_true", help="run the VERIFY gate only; do not rebuild")
    args = ap.parse_args(argv)
    targets = resolve_targets(args.target)

    if not args.check:
        md = make_renderer()
        write_style()
        for site in targets:
            n = build_site(site, md)
            print(f"built {site.key}: {n} pages -> {site.out.relative_to(ROOT)}")
        build_landing(resolve_targets("both") if args.target == "both" else targets)
        print(f"built landing -> {(DOCS_OUT / 'index.html').relative_to(ROOT)}")

    problems = verify(targets)
    if problems:
        print(f"\nVERIFY FAILED ({len(problems)} problem(s)):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(
        f"\nVERIFY OK: {sum(1 for s in targets for _ in s.out.rglob('*.html'))} "
        "pages, source<->output parity, links resolve, callouts+mermaid rendered."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
