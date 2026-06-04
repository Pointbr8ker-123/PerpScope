import sys
import os
import math
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from calculate_rho import (
    calculate_rho,
    get_signal,
    THRESHOLDS,
    KAPPA,
    IOTA,
    GAMMA,
    RISK_FREE_RATE_8HR,
    PERIODS_PER_YEAR,
)


class TestCalculateRho:
    """Tests for the He et al. (2024) no-arbitrage deviation measure."""

    def test_zero_premium_returns_small_negative_rho(self):
        """
        When futures price equals spot price, premium index is 0.
        rho shpild be near 0 but slightly negative due to the risk-free rate
        and clamp mechanism.
        """
        rho = calculate_rho(100.0, 100.0)
        assert rho is not None
        assert not math.isnan(rho)
        # abs(rho) should be a very small value
        assert abs(rho) < 0.5

    def test_positive_premium_gives_positive_rho(self):
        """
        When futures price > spot price, rho should be positive - 
        i.e SHORT_PERP_LONG_SPOT signal.
        """
        rho = calculate_rho(101.0, 100.0)
        assert rho > 0

    def test_negative_premium_gives_negative_rho(self):
        """
        When futures price < spot price, rho should be negative - 
        i.e LONG_PERP_SHORT_SPOT signal.
        """
        rho = calculate_rho(99.0, 100.0)
        assert rho < 0

    def test_large_premium_exceeds_retail_threshold(self):
        """
        A 2% premium for instance should produce rho value well above the
        retail threshold, generating a SHORT_PERP_LONG_SPOT signal.
        """
        rho    = calculate_rho(102.0, 100.0)
        signal = get_signal(rho, 'high')
        assert signal == 'SHORT_PERP_LONG_SPOT'

    def test_small_premium_within_threshold_is_neutral(self):
        """
        A very tiny premium should produce a NEUTRAL signal.
        """
        rho    = calculate_rho(100.005, 100.0)
        signal = get_signal(rho, 'high')
        assert signal == 'NEUTRAL'

    @pytest.mark.parametrize(
            "futures,spot",
            [
                (0, 100.0),
                (100.0, 0),
                (-1.0, 100.0),
                (100.0, -1.0)
            ]
    )
    def test_zero_or_negative_prices_return_nan(self, futures, spot):
        """
        Invalid prices (zero or negative) should return NaN, 
        not crash or return nonsense values.
        """
        assert math.isnan(calculate_rho(futures, spot))

    def test_extreme_premium_returns_nan(self):
        """
        Premiums above 20% might indicate corrupted data.
        It should return NaN rather than a large rho value.
        """
        rho = calculate_rho(130.0, 100.0) # i.e ~23% premium
        assert math.isnan(rho)

    def test_annualization_factor(self):
        """
        rho should be annualized bu multiplying by 1095
        """
        assert PERIODS_PER_YEAR == 1095

    def test_thresholds_are_ordered_correctly(self):
        """
        Higher cost tiers should have higher thresholds.
        Retail traders need bigger deviations to profit than
        institutional traders because they pay higher fees.
        """
        assert THRESHOLDS['high'] > THRESHOLDS['medium']
        assert THRESHOLDS['medium'] > THRESHOLDS['low']
        assert THRESHOLDS['low'] > THRESHOLDS['no_fee']
        assert THRESHOLDS['no_fee'] == 0.0

    def test_get_signal_neutral_for_zero_rho(self):
        assert get_signal(0.0) == 'NEUTRAL'

    def test_get_signal_short_for_large_positive_rho(self):
        assert get_signal(5.0) == 'SHORT_PERP_LONG_SPOT'

    def test_get_signal_long_for_large_negative_rho(self):
        assert get_signal(-5.0) == 'LONG_PERP_SHORT_SPOT'

    def test_signal_on_threshold_tier(self):
        """
        The same rho value that is NEUTRAL for a retail trader (i.e high)
        sould be an opportunity for a market maker (i.e no_fee) since the
        market makers don't pay fees, therefore everything above 0 is an
        opportunity for them.
        """
        rho = 0.3   # tiny positive deviation
        assert get_signal(rho, 'high') == 'NEUTRAL'
        assert get_signal(rho, 'no_fee') == 'SHORT_PERP_LONG_SPOT'


class TestRhoCalculationAccuracy:
    """
    These tests verify that the rho calculation is accurate and in accordance
    with the formula from the He et al. research paper
    """

    def test_larger_premium_gives_larger_rho(self):
        """Larger futures premium should give larger rho deviation."""
        rho_small = calculate_rho(100.5, 100.0)     # 0.5% premium
        rho_large = calculate_rho(101.5, 100.0)     # 1.5% premium
        assert abs(rho_large) > abs(rho_small)

    def test_rho_calculation_consistency(self):
        """
        Tests the consistency and accuracy of the 'calculate_rho()' 
        function.
        """
        futures_price = 101.0
        spot_price    = 100.0
        premium       = (futures_price - spot_price) / futures_price

        sign_iota_minus_rfr = float(np.sign(IOTA - RISK_FREE_RATE_8HR))
        rho_per_period      = KAPPA * premium + sign_iota_minus_rfr * GAMMA - RISK_FREE_RATE_8HR
        expected_rho        = rho_per_period * PERIODS_PER_YEAR

        assert calculate_rho(futures_price, spot_price) == expected_rho


if __name__ == "__main__":
    ...