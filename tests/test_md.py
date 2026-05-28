from bdboard import md


def test_render_converts_single_escaped_newlines_to_real_line_breaks() -> None:
    html = md.render("line one\\n\\nline two")

    assert "<p>line one</p>" in html
    assert "<p>line two</p>" in html


def test_render_preserves_double_escaped_newline_literal() -> None:
    html = md.render(r"show literal \\n please")

    assert "show literal \\n please" in html
