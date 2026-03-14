"""Tests del criterio de Kelly."""

import pytest

from app.risk.kelly import kelly_crypto, kelly_prediction, size_position


class TestKellyCrypto:
    def test_positive_edge(self):
        """65% win rate, 2:1 reward/risk → Kelly positivo."""
        f = kelly_crypto(p_win=0.65, take_profit_pct=0.04, stop_loss_pct=0.02)
        assert f > 0
        assert f == pytest.approx(0.475, abs=0.01)

    def test_no_edge(self):
        """50% win rate, 1:1 reward/risk → Kelly = 0."""
        f = kelly_crypto(p_win=0.50, take_profit_pct=0.02, stop_loss_pct=0.02)
        assert f == pytest.approx(0.0, abs=0.01)

    def test_negative_edge(self):
        """30% win rate, 1:1 → Kelly negativo → retorna 0."""
        f = kelly_crypto(p_win=0.30, take_profit_pct=0.02, stop_loss_pct=0.02)
        assert f == 0.0

    def test_high_reward_low_prob(self):
        """40% win rate, 3:1 reward → debe tener edge."""
        f = kelly_crypto(p_win=0.40, take_profit_pct=0.06, stop_loss_pct=0.02)
        assert f > 0

    def test_invalid_inputs(self):
        assert kelly_crypto(0, 0.04, 0.02) == 0.0
        assert kelly_crypto(1, 0.04, 0.02) == 0.0
        assert kelly_crypto(0.6, 0, 0.02) == 0.0
        assert kelly_crypto(0.6, 0.04, 0) == 0.0


class TestKellyPrediction:
    def test_buy_yes_with_edge(self):
        """Estimamos 60%, mercado dice 45% → edge para comprar YES."""
        f = kelly_prediction(p_estimated=0.60, market_price=0.45, direction="BUY_YES")
        assert f > 0

    def test_buy_no_with_edge(self):
        """Estimamos 30%, mercado dice 60% → edge para comprar NO."""
        f = kelly_prediction(p_estimated=0.30, market_price=0.60, direction="BUY_NO")
        assert f > 0

    def test_no_edge(self):
        """Estimamos 50%, mercado dice 50% → sin edge."""
        f = kelly_prediction(p_estimated=0.50, market_price=0.50, direction="BUY_YES")
        assert f == pytest.approx(0.0, abs=0.01)

    def test_wrong_direction(self):
        """Estimamos 40% pero queremos comprar YES → negativo → 0."""
        f = kelly_prediction(p_estimated=0.40, market_price=0.50, direction="BUY_YES")
        assert f == 0.0


class TestSizePosition:
    def test_normal_sizing(self):
        """Capital $300, Kelly 0.475, fractional 0.25, cap 3%."""
        size = size_position(
            kelly_fraction=0.475, capital=300, fractional_kelly=0.25, max_pct=0.03
        )
        # 0.475 * 0.25 = 0.119 → capped at 0.03 → 300 * 0.03 = $9
        assert size == pytest.approx(9.0, abs=0.01)

    def test_small_kelly(self):
        """Kelly pequeño, no llega al cap."""
        size = size_position(
            kelly_fraction=0.08, capital=300, fractional_kelly=0.25, max_pct=0.03
        )
        # 0.08 * 0.25 = 0.02 → 300 * 0.02 = $6
        assert size == pytest.approx(6.0, abs=0.01)

    def test_zero_kelly(self):
        size = size_position(kelly_fraction=0, capital=300)
        assert size == 0.0

    def test_large_capital(self):
        size = size_position(
            kelly_fraction=0.5, capital=10000, fractional_kelly=0.25, max_pct=0.03
        )
        # 0.5 * 0.25 = 0.125 → capped at 0.03 → 10000 * 0.03 = $300
        assert size == pytest.approx(300.0, abs=0.01)
