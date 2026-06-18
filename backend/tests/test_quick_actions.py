"""Phase 12h — Command Center quick actions."""

from thread.services.quick_actions import build_quick_actions


def test_build_quick_actions_includes_core_links():
    actions = build_quick_actions(opportunities=[], intel_signals=[])
    by_id = {a.id: a for a in actions}
    assert by_id["track"].href == "/pulse#potential-watchlist"
    assert by_id["insights"].href == "/insights"
    assert by_id["vault"].href == "/knowledge"
    assert by_id["research"].enabled is False


def test_research_links_to_latest_opp():
    actions = build_quick_actions(
        opportunities=[{"id": "abc-123", "name": "Army Cloud"}],
        intel_signals=[],
    )
    research = next(a for a in actions if a.id == "research")
    assert research.enabled is True
    assert research.href == "/opportunities/abc-123?tab=research"


def test_hot_signal_inserts_track_hot_action():
    actions = build_quick_actions(
        opportunities=[],
        intel_signals=[
            {"months_to_end": 12, "title": "Warm Co"},
            {"months_to_end": 4, "title": "Hot Co"},
        ],
    )
    ids = [a.id for a in actions]
    assert "track-hot" in ids
    hot = next(a for a in actions if a.id == "track-hot")
    assert "Hot Co" in hot.hint