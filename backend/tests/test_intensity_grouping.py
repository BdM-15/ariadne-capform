"""Capture intensity buyer-level grouping."""

from thread.intel.charts import _intensity_buyer_grouping, _intensity_quadrant
from thread.intel.facet_query import query_from_dict


def test_intensity_defaults_to_awarding_office_for_broad_slice():
    q = query_from_dict({"id": "n", "name": "n", "naics_codes": "561210"})
    _, hone, level, label = _intensity_buyer_grouping(q)
    assert hone == "awarding_office"
    assert level == "office"
    assert "awarding" in label.lower()


def test_intensity_uses_funding_office_when_only_funding_set():
    q = query_from_dict(
        {
            "id": "n",
            "name": "n",
            "naics_codes": "561210",
            "funding_office": "Office of Science",
        }
    )
    _, hone, level, _ = _intensity_buyer_grouping(q)
    assert hone == "funding_office"
    assert level == "office"


def test_intensity_quadrant_hot_above_both_medians():
    assert _intensity_quadrant(10, 5.0, median_actions=5, median_millions=3.0) == "hot"
    assert _intensity_quadrant(2, 8.0, median_actions=5, median_millions=3.0) == "high_value"
    assert _intensity_quadrant(10, 1.0, median_actions=5, median_millions=3.0) == "high_volume"
    assert _intensity_quadrant(1, 1.0, median_actions=5, median_millions=3.0) == "watch"