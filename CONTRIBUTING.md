# Contributing to bdboard

Thanks for your interest in improving bdboard! This is a small, focused
project — a local-first dashboard for [bd (beads)](https://github.com/gastownhall/beads)
workspaces — and contributions are welcome.

## Getting started

``````sh
git clone <your-fork-url>
cd bdboard
bd bootstrap --yes         # hydrate the bead DB — a fresh clone has none (see note below)
make install               # uv venv + editable install
source .venv/bin/activate  # activate the venv
make test                  # run the test suite
bdboard                    # run it against this repo's own .beads workspace
```

> **Don't skip `bd bootstrap`.** A fresh clone ships **no** bead database
> (`.beads/embeddeddolt/` is gitignored), so `bd list` reports `no beads
> database found` and `bdboard` comes up showing an **empty board** until you
> hydrate once. The test suite passes without it (tests use fixtures), but the
> running board will be blank. See the README's
> [Getting the bead history (fresh clone)](README.md#getting-the-bead-history-fresh-clone)
> for details.

See the [README](README.md) for prerequisites (you'll need the `bd` binary on
your `PATH`, Python ≥ 3.11, and `uv`).

## Before you open a pull request

Run the same checks CI enforces:

```sh
make code-health      # lint + format-check + dead-code + tests + duplication + audit
```

- **Lint & format** — `ruff check --fix` and `ruff format .` (or `make lint` /
  `make fmt`). CI runs these in check-only mode and will fail on violations.
- **Tests** — add or update tests for any behavior change (`make test`).
- **Accessibility** — UI changes should preserve WCAG AA contrast; there are
  contrast tests under `tests/` you can mirror.
- **File size** — keep modules focused; the project favors splitting files that
  grow past ~600 lines when it improves cohesion.

## Commit & PR guidelines

- Write clear, imperative commit messages describing the *why*, not just the
  *what*.
- Keep changes scoped to one logical concern per PR where practical.
- Update the README or `docs/` when you change user-facing behavior.

## Design decisions

Architectural rationale lives in [`docs/decisions/`](docs/decisions/) as ADRs.
Start with the [ADR index & guidelines](docs/decisions/README.md) (it explains
when to write an ADR vs. a `docs/design/<bead-id>/` doc) and copy
[`0000-template.md`](docs/decisions/0000-template.md) for a new one.
If you're proposing a significant structural change, add an ADR.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
