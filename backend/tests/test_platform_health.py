"""Phase 12e — platform health widget."""

import pytest

from thread.services.platform_health import build_platform_health_widget


@pytest.mark.asyncio
async def test_platform_health_widget_shape(db_session, settings):
    widget = await build_platform_health_widget(db_session, settings)
    assert widget.status in ("ok", "degraded", "blocked")
    assert isinstance(widget.blockers, tuple)
    assert isinstance(widget.migration_pct, float)