"""Analytics sub-view registry — the single extension point for the
Analytics tab (bdboard-ove7).

The Analytics page (``/analytics``) hosts multiple analytics/history
sub-views behind one in-page switcher, so the primary nav stays flat as the
analytics surface grows (parent epic bdboard-e47e). Rather than hard-code each
sub-view into the route/template, sub-views are **data-driven** from the
:data:`ANALYTICS_VIEWS` tuple below.

Extension point — adding a new sub-view is a small ADDITIVE change:

    1. Write its shell partial under ``templates/partials/`` — a self-contained
       region that lazy-loads its own data via HTMX (``hx-trigger="load,
       refresh from:body"``) so it hydrates on switch-in AND live-updates on
       SSE, exactly like ``partials/analytics_history.html``.
    2. Append ONE :class:`AnalyticsView` entry to :data:`ANALYTICS_VIEWS`.

That's it: the switcher, routing, URL/deep-link handling, and active-state
wiring are all driven off the registry, so no route handler, no
``analytics.html``, and no switcher markup needs to change. The first entry is
the default view (served when ``?view=`` is missing or unknown).

Each sub-view OWNS all of its chrome (including any stats strip) inside its own
shell partial — the Analytics masthead stays generic so it never needs a
per-view special case. See :func:`resolve_view` for the lookup +
graceful-fallback behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyticsView:
    """One selectable Analytics sub-view.

    Attributes:
        key: URL token (``?view=<key>``). Stable, lowercase, no spaces — it is
            the deep-link identity and the switcher's active-state key.
        label: Human-readable switcher button text.
        partial: Template path of the sub-view's shell partial, included by
            ``partials/analytics_panel.html``. The shell is responsible for
            lazy-loading its own data region(s).
    """

    key: str
    label: str
    partial: str


# Ordered registry. The FIRST entry is the default sub-view (served for a
# missing/unknown ?view=). Order here is the order the switcher renders.
#
# History is the first sub-view (migrated from the former standalone /history
# page). Interactions follows in task_analytics_interactions — when it lands it
# is literally one more AnalyticsView entry + its shell partial, nothing else.
ANALYTICS_VIEWS: tuple[AnalyticsView, ...] = (
    AnalyticsView(
        key="history",
        label="History",
        partial="partials/analytics_history.html",
    ),
)

DEFAULT_VIEW: AnalyticsView = ANALYTICS_VIEWS[0]

_BY_KEY: dict[str, AnalyticsView] = {v.key: v for v in ANALYTICS_VIEWS}


def resolve_view(key: str | None) -> AnalyticsView:
    """Resolve a ``?view=`` token to an :class:`AnalyticsView`.

    A missing or unknown key degrades to :data:`DEFAULT_VIEW` so a bad/stale
    deep link can never 404 or render an empty panel — it just lands on the
    first sub-view. The lookup is case-insensitive on the trimmed token.
    """
    norm = (key or "").strip().lower()
    return _BY_KEY.get(norm, DEFAULT_VIEW)
