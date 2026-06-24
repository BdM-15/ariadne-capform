"""Phase 2d — deterministic Shipley MS1 gate cards on Overview."""

from thread.services.insights_overview import overview_capture_verdict, overview_shipley_cards


def _motion_brief(**overrides: object) -> dict:
    base = {
        "direct_prime_pct": 45.0,
        "sub_only_pct": 30.0,
        "vehicle_pct": 10.0,
        "teaming_targets": [
            {
                "bucket": "8(A) SOLE SOURCE",
                "millions": 12.0,
                "primes": [{"recipient": "Small Prime LLC", "millions": 8.0}],
            }
        ],
    }
    base.update(overrides)
    return base


def test_shipley_cards_returns_four_ms1_gates():
    overview = {
        "agency_intensity": {"hot_agencies": ["Department of Defense"]},
        "pricing_buckets": [
            {"bucket": "firm_fixed", "millions": 40.0},
            {"bucket": "time_materials", "millions": 20.0},
        ],
        "expiring_timeline": {"insight": "Peak cluster Mar 2026 — $4.5M across 12 actions"},
    }
    rows = (
        {
            "recipient": "Flex Co",
            "months_to_end": 4,
            "obligation": 800_000,
            "shape_gate": "shape_now",
            "shape_reason": "Non-fixed expiring under pressure",
        },
        {
            "recipient": "Hot Inc",
            "months_to_end": 2,
            "obligation": 600_000,
            "shape_gate": "monitor",
        },
    )
    cards = overview_shipley_cards(
        overview,
        motion_brief=_motion_brief(),
        pipeline={"count": 25, "millions": 18.5},
        expiring_rows=rows,
    )
    assert len(cards) == 4
    assert {c["id"] for c in cards} == {
        "prime_lane",
        "teaming_lane",
        "shape_window",
        "recompete_clock",
    }
    assert cards[0]["gate"] == "pursue"
    assert cards[1]["gate"] == "monitor"  # 30% sub < 35% pursue threshold
    assert cards[2]["gate"] == "pursue"
    assert cards[3]["gate"] == "pursue"


def test_shipley_prime_lane_defers_on_thin_open_competed():
    cards = overview_shipley_cards(
        {},
        motion_brief=_motion_brief(direct_prime_pct=8.0, sub_only_pct=5.0, vehicle_pct=5.0, teaming_targets=[]),
        pipeline={"count": 0, "millions": 0.0},
        expiring_rows=(),
    )
    prime = next(c for c in cards if c["id"] == "prime_lane")
    assert prime["gate"] == "defer"


def test_overview_capture_verdict_includes_shipley():
    overview = {
        "kpis": {"millions": 50.0, "award_count": 100, "agency_count": 3},
        "spend_trend": [],
        "agency_intensity": {"hot_agencies": []},
        "top_recipients": [],
        "set_aside": [],
        "motion": {
            "channels": [
                {"channel": "open_competed", "millions": 30.0},
                {"channel": "set_aside_non_competed", "millions": 20.0},
            ],
        },
    }
    verdict = overview_capture_verdict(
        overview,
        pipeline={"count": 5, "millions": 2.0},
        expiring_rows=({"recipient": "A", "months_to_end": 3, "obligation": 100_000},),
    )
    assert len(verdict["shipley"]) == 4
    assert verdict["shipley"][0]["gate_label"] in ("Pursue", "Monitor", "Defer")