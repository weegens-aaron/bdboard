"""Analytics sub-view registry — the single extension point for the
Analytics tab (bdboard-ove7), with conditional registration (bdboard-8l60).

The Analytics page (``/analytics``) hosts multiple analytics/history
sub-views behind one in-page switcher, so the primary nav stays flat as the
analytics surface grows (parent epic bdboard-e47e). Rather than hard-code each
sub-view into the route/template, the active set of sub-views is **built
per-request** from the workspace's data via :func:`build_views`.

Conditional registration (bdboard-8l60 decision — Option A):
    History is **always** present and is the default sub-view. Interactions is
    a *reward-bearing* view — it only earns a switcher chip + panel when the
    workspace's ``.beads/interactions.jsonl`` actually carries reward-bearing
    entries (``llm_call`` / ``tool_call`` / ``label``). A log that is empty,
    missing, or 100% ``field_change`` (the common real-world case) does NOT
    register Interactions: the field_change stream is redundant with per-bead
    ``bd history`` (surfaced in the bead Audit/Lifecycle modal), so there is no
    value in a global field_change feed. See :func:`has_reward_bearing_interactions`.

Extension point — adding a new sub-view is a small ADDITIVE change:

    1. Write its shell partial under ``templates/partials/`` — a self-contained
       region that lazy-loads its own data via HTMX (``hx-trigger="load,
       refresh from:body"``) so it hydrates on switch-in AND live-updates on
       SSE, exactly like ``partials/analytics_history.html``.
    2. Add ONE :class:`AnalyticsView` to the list :func:`build_views` returns
       (unconditionally if it is always-on like History, or behind a cheap
       per-workspace predicate like Interactions).

That's it: the switcher, routing, URL/deep-link handling, and active-state
wiring are all driven off the built registry, so no route handler, no
``analytics.html``, and no switcher markup needs to change. History stays the
first/default view (served when ``?view=`` is missing or unknown, OR when a
stale ``?view=interactions`` lands while Interactions is unregistered).

Each sub-view OWNS all of its chrome (including any stats strip) inside its own
shell partial — the Analytics masthead stays generic so it never needs a
per-view special case. See :func:`resolve_view` for the lookup +
graceful-fallback behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bdboard import interactions


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


# History is the always-on, default sub-view (migrated from the former
# standalone /history page). It never depends on workspace data — every
# workspace has bd history — so it is registered unconditionally.
HISTORY_VIEW: AnalyticsView = AnalyticsView(
    key="history",
    label="History",
    partial="partials/analytics_history.html",
)

# Interactions is the reward-bearing sub-view (migrated from the former
# standalone /interactions page, bdboard-vtd4). It is registered ONLY when the
# workspace's interaction log carries reward-bearing entries — see
# build_views / has_reward_bearing_interactions.
INTERACTIONS_VIEW: AnalyticsView = AnalyticsView(
    key="interactions",
    label="Interactions",
    partial="partials/analytics_interactions.html",
)

# The default sub-view served for a missing/unknown ?view=, and the safe
# degrade target when a registered view can't be resolved. History is always
# present, so it is always a valid default.
DEFAULT_VIEW: AnalyticsView = HISTORY_VIEW

# The interaction kinds that make the Interactions sub-view worth surfacing:
# the SFT/RL "why did the agent do that" reward signal. The legacy
# ``field_change`` kind is deliberately excluded — it is redundant with
# per-bead ``bd history`` (the bead Audit/Lifecycle modal), so a field_change-
# only log does not earn the sub-view.
REWARD_BEARING_KINDS: frozenset[str] = frozenset({"llm_call", "tool_call", "label"})


def has_reward_bearing_interactions(beads_dir: Path) -> bool:
    """Return True iff the workspace's interaction log has a reward-bearing kind.

    Reuses :func:`interactions.read_interactions` + :func:`interactions.kind_counts`
    (a single on-demand file read, no caching — matching how History reads
    snapshots) and checks whether any of :data:`REWARD_BEARING_KINDS` is
    present. An empty, missing, or 100%-``field_change`` log returns False, so
    the Interactions sub-view stays unregistered in the common real-world case.
    """
    counts = interactions.kind_counts(interactions.read_interactions(beads_dir))
    return any(kind in counts for kind in REWARD_BEARING_KINDS)


def build_views(beads_dir: Path) -> tuple[AnalyticsView, ...]:
    """Build the ordered registry of Analytics sub-views for a workspace.

    The build is per-request (conditional registration is per-workspace data),
    so call it with the live ``beads_dir`` in scope rather than caching a
    module-level tuple. It is cheap: the only data touch is the reward-bearing
    probe, itself a single on-demand log read.

    The FIRST entry is always History (the default sub-view + switcher order
    origin). Interactions is appended only when the workspace has reward-bearing
    interactions.
    """
    views: list[AnalyticsView] = [HISTORY_VIEW]
    if has_reward_bearing_interactions(beads_dir):
        views.append(INTERACTIONS_VIEW)
    return tuple(views)


def resolve_view(key: str | None, views: tuple[AnalyticsView, ...]) -> AnalyticsView:
    """Resolve a ``?view=`` token to one of the registered ``views``.

    A missing or unknown key — including a stale ``?view=interactions`` that
    lands while Interactions is *unregistered* for this workspace — degrades to
    the first registered view (History) so a bad/stale deep link can never 404
    or render an empty panel. The lookup is case-insensitive on the trimmed
    token. ``views`` should come from :func:`build_views`; an empty tuple
    degrades to :data:`DEFAULT_VIEW` as a defensive last resort.
    """
    norm = (key or "").strip().lower()
    by_key = {v.key: v for v in views}
    fallback = views[0] if views else DEFAULT_VIEW
    return by_key.get(norm, fallback)
