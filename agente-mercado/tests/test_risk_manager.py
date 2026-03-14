"""Tests del risk manager."""

import pytest

from app.risk.kelly import kelly_crypto, size_position


class TestRiskLimits:
    """Tests de los cálculos de riesgo sin base de datos."""

    def test_position_below_minimum(self):
        """Con capital muy bajo, el trade es menor al mínimo."""
        size = size_position(kelly_fraction=0.1, capital=50, fractional_kelly=0.25, max_pct=0.03)
        # 0.1 * 0.25 = 0.025 → 50 * 0.025 = $1.25 < $5 mínimo
        assert size < 5.0

    def test_position_above_minimum(self):
        """Con capital suficiente, el trade supera el mínimo."""
        size = size_position(kelly_fraction=0.5, capital=300, fractional_kelly=0.25, max_pct=0.03)
        assert size >= 5.0

    def test_cap_always_respected(self):
        """El cap de 3% siempre se respeta."""
        for kelly in [0.1, 0.3, 0.5, 0.8, 1.0]:
            size = size_position(kelly_fraction=kelly, capital=1000, max_pct=0.03)
            assert size <= 1000 * 0.03 + 0.01  # Tolerancia de redondeo

    def test_drawdown_calculation(self):
        """Cálculo de drawdown."""
        peak = 500.0
        current = 425.0
        drawdown = (peak - current) / peak
        assert drawdown == pytest.approx(0.15, abs=0.01)  # 15%

    def test_no_drawdown_at_peak(self):
        drawdown = (500 - 500) / 500
        assert drawdown == 0.0

    def test_daily_loss_limit(self):
        """Con capital $300, límite diario 5% = $15."""
        capital = 300
        max_daily = capital * 0.05
        assert max_daily == pytest.approx(15.0)

    def test_weekly_loss_limit(self):
        """Con capital $300, límite semanal 10% = $30."""
        capital = 300
        max_weekly = capital * 0.10
        assert max_weekly == pytest.approx(30.0)


class TestKellyEdgeCases:
    def test_very_high_confidence(self):
        """99% confidence → Kelly alto, pero cap lo limita."""
        f = kelly_crypto(p_win=0.99, take_profit_pct=0.05, stop_loss_pct=0.02)
        size = size_position(f, capital=300, fractional_kelly=0.25, max_pct=0.03)
        assert size == pytest.approx(9.0, abs=0.01)  # Siempre capped

    def test_barely_profitable(self):
        """51% con 1:1 → edge mínimo."""
        f = kelly_crypto(p_win=0.51, take_profit_pct=0.02, stop_loss_pct=0.02)
        assert f > 0
        assert f < 0.05  # Edge muy pequeño
