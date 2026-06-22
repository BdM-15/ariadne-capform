"""Operator NAICS portfolio — explicit operator config."""

from thread.intel.operator_profile import (
    OperatorProfile,
    load_operator_profile,
    save_naics_portfolio_from_text,
    save_operator_profile,
)


def test_save_and_load_naics_portfolio(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    save_naics_portfolio_from_text(settings, "541512, 541511; 561210")
    profile = load_operator_profile(settings)
    assert profile.naics_portfolio == ("541512", "541511", "561210")


def test_naics_portfolio_dedupes_and_caps(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    raw = ", ".join(["541512"] * 20)
    save_operator_profile(settings, OperatorProfile(naics_portfolio=("541512", "541511")))
    profile = save_naics_portfolio_from_text(settings, raw)
    assert len(profile.naics_portfolio) <= 12
    assert profile.naics_portfolio[0] == "541512"