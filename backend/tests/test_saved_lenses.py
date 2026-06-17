"""Phase 12f — saved lenses + multi-NAICS radar."""

from thread.intel.saved_lenses import (
    load_saved_lenses,
    naics_codes_for_radar,
    radar_lens_summary,
)


def test_builtin_lenses_not_single_naics(settings):
    codes = naics_codes_for_radar(settings)
    assert len(codes) >= 2
    assert "561210" in codes


def test_load_saved_lenses_returns_named_presets(settings):
    lenses = load_saved_lenses(settings)
    assert len(lenses) >= 2
    assert all(lens.naics_codes for lens in lenses)
    summary = radar_lens_summary(settings)
    assert summary


def test_custom_lenses_file_overrides_builtin(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    lens_dir = settings.resolve(settings.thread_state_dir)
    lens_dir.mkdir(parents=True)
    (lens_dir / "saved_lenses.json").write_text(
        '[{"id": "custom", "name": "Custom lane", "naics_codes": ["541330", "541611"]}]',
        encoding="utf-8",
    )
    codes = naics_codes_for_radar(settings)
    assert codes == ["541330", "541611"]
    assert radar_lens_summary(settings) == "Custom lane"