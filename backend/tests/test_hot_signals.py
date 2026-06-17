from thread.services.hot_signals import build_hot_signals_widget, filter_hot_signals


def test_filter_hot_signals():
    signals = [
        {"months_to_end": 4, "title": "Hot"},
        {"months_to_end": 10, "title": "Warm"},
        {"months_to_end": 6, "title": "Edge"},
    ]
    hot = filter_hot_signals(signals)
    assert len(hot) == 2
    assert hot[0]["title"] == "Hot"


def test_hot_widget_needs_attention_when_hot_exists():
    widget = build_hot_signals_widget(
        intel_signals=[{"months_to_end": 3, "title": "A", "agency": "Army"}],
        intel_live=True,
        lens_summary="2 saved lenses",
    )
    assert widget.hot_count == 1
    assert widget.needs_attention is True
    assert widget.preview[0]["title"] == "A"