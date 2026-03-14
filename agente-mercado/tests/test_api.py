"""Tests básicos de los endpoints de la API."""

import pytest

from app.api.auth import create_token


class TestAuth:
    def test_create_token(self):
        token = create_token("test-user")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_token_default_subject(self):
        token = create_token()
        assert isinstance(token, str)


class TestSchemas:
    def test_config_update_partial(self):
        from app.api.schemas import ConfigUpdate

        config = ConfigUpdate(deviation_threshold=0.10)
        assert config.deviation_threshold == 0.10
        assert config.fractional_kelly is None
        assert config.max_per_trade_pct is None

    def test_config_update_full(self):
        from app.api.schemas import ConfigUpdate

        config = ConfigUpdate(
            deviation_threshold=0.06,
            fractional_kelly=0.30,
            max_per_trade_pct=0.05,
            max_daily_loss_pct=0.08,
            max_weekly_loss_pct=0.15,
            max_drawdown_pct=0.20,
            max_concurrent_positions=15,
            min_volume_usd=100000,
            min_confidence=0.70,
        )
        assert config.deviation_threshold == 0.06
        assert config.max_concurrent_positions == 15
