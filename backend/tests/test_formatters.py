"""Display formatters — compact money and counts."""

from thread.ui.formatters import format_count, format_money, format_money_from_millions


def test_format_money_raw_dollars():
    assert format_money(12_500) == "$12K"
    assert format_money(2_500_000) == "$2.5M"
    assert format_money(22_900_000_000) == "$22.9B"


def test_format_money_from_millions_slice_scale():
    assert format_money_from_millions(120.5) == "$120.5M"
    assert format_money_from_millions(350_188.1) == "$350.2B"
    assert format_money_from_millions(22_938.3) == "$22.9B"
    assert format_money_from_millions(52_184.8) == "$52.2B"


def test_format_count_compact():
    assert format_count(12) == "12"
    assert format_count(1_234) == "1.2k"
    assert format_count(366_514) == "366.5k"
    assert format_count(11_934) == "11.9k"