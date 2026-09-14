import math

import pytest

from tools.financial_calculator import (
    calculate_combined_metric,
    calculate_deal_economics,
    calculate_growth_rate,
    calculate_margin,
    calculate_precision_flag,
    calculate_ramp_adjusted_value,
    calculate_revenue_scenario,
    calculate_savings_scenario,
)


def test_growth_rate_basic():
    result = calculate_growth_rate(100, 121, periods=2)
    assert result["growth_rate_pct"] == pytest.approx(10.0, abs=0.01)


def test_growth_rate_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        calculate_growth_rate(0, 100, 1)
    with pytest.raises(ValueError):
        calculate_growth_rate(100, 121, 0)


def test_margin_basic():
    result = calculate_margin(revenue=1000, cost_or_profit=150, margin_type="operating")
    assert result["margin_pct"] == pytest.approx(15.0)


def test_margin_rejects_zero_revenue():
    with pytest.raises(ValueError):
        calculate_margin(0, 100)


def test_savings_scenario_ordering_and_values():
    result = calculate_savings_scenario(1_000_000, 0.02, 0.05, 0.08)
    assert result["low"] == 20_000
    assert result["base"] == 50_000
    assert result["high"] == 80_000
    assert result["low"] <= result["base"] <= result["high"]


def test_savings_scenario_rejects_out_of_range_pct():
    with pytest.raises(ValueError):
        calculate_savings_scenario(1_000_000, -0.1, 0.05, 0.08)
    with pytest.raises(ValueError):
        calculate_savings_scenario(1_000_000, 0.02, 0.05, 1.5)


def test_revenue_scenario_with_margin_conversion():
    result = calculate_revenue_scenario(10_000_000, 0.01, 0.02, 0.03, incremental_margin_pct=0.2)
    assert result["low"] == 20_000
    assert result["base"] == 40_000
    assert result["high"] == 60_000


def test_revenue_scenario_default_margin_is_full_revenue():
    result = calculate_revenue_scenario(1_000_000, 0.05, 0.05, 0.05, incremental_margin_pct=1.0)
    assert result["base"] == 50_000


def test_combined_metric_no_adjustment():
    result = calculate_combined_metric(600, 400, adjustment_pct=0.0)
    assert result["combined_value"] == 1000


def test_combined_metric_with_dis_synergy():
    result = calculate_combined_metric(600, 400, adjustment_pct=-0.05)
    assert result["combined_value"] == pytest.approx(950.0)


def test_precision_flag_catches_false_precision():
    result = calculate_precision_flag(3_487_213, sig_figs_allowed=3)
    assert result["flagged"] is True


def test_precision_flag_allows_rounded_estimate():
    result = calculate_precision_flag(3_500_000, sig_figs_allowed=3)
    assert result["flagged"] is False


def test_deal_economics_basic():
    result = calculate_deal_economics(total_value_creation=237_000_000, deal_value=13_700_000_000)
    assert result["value_creation_pct_of_deal"] == pytest.approx(1.73, abs=0.01)


def test_deal_economics_rejects_nonpositive_deal_value():
    with pytest.raises(ValueError):
        calculate_deal_economics(100, 0)
    with pytest.raises(ValueError):
        calculate_deal_economics(100, -1)


def test_ramp_adjusted_value_basic():
    result = calculate_ramp_adjusted_value(100_000, year_1_pct=0.4, year_2_pct=0.8, year_3_pct=1.0, cost_to_achieve=50_000)
    assert result["year_1"] == 40_000
    assert result["year_2"] == 80_000
    assert result["year_3"] == 100_000
    assert result["cumulative_3yr"] == 220_000
    assert result["net_3yr_value"] == 170_000


def test_ramp_adjusted_value_no_ramp_no_cost():
    result = calculate_ramp_adjusted_value(100_000, 1.0, 1.0, 1.0)
    assert result["cumulative_3yr"] == 300_000
    assert result["net_3yr_value"] == 300_000


def test_ramp_adjusted_value_rejects_negative_pct():
    with pytest.raises(ValueError):
        calculate_ramp_adjusted_value(100_000, -0.1, 0.8, 1.0)
