import pytest

from agent.sensitivity import compute_scenario_total, compute_tornado_rows
from schemas.analysis_models import Category, Difficulty, EstimatedValue, ValueOpportunity


def _cost_opportunity() -> ValueOpportunity:
    return ValueOpportunity(
        title="Consolidate distribution",
        category=Category.COST_SYNERGY,
        rationale="r",
        estimated_value=EstimatedValue(low=150_000_000, base=225_000_000, high=300_000_000),
        implementation_difficulty=Difficulty.MEDIUM,
        time_horizon="12-18 months",
        calculation_method="calculate_savings_scenario",
        calculation_inputs={
            "baseline_cost": 1_500_000_000,
            "reduction_pct_low": 0.10,
            "reduction_pct_base": 0.15,
            "reduction_pct_high": 0.20,
        },
    )


def _revenue_opportunity() -> ValueOpportunity:
    return ValueOpportunity(
        title="Cross-sell",
        category=Category.REVENUE_SYNERGY,
        rationale="r",
        estimated_value=EstimatedValue(low=8_000_000, base=12_000_000, high=16_000_000),
        implementation_difficulty=Difficulty.LOW,
        time_horizon="0-6 months",
        calculation_method="calculate_revenue_scenario",
        calculation_inputs={
            "baseline_revenue": 800_000_000,
            "uplift_pct_low": 0.01,
            "uplift_pct_base": 0.015,
            "uplift_pct_high": 0.02,
            "incremental_margin_pct": 1.0,
        },
    )


def _dis_synergy_opportunity() -> ValueOpportunity:
    return ValueOpportunity(
        title="Customer attrition",
        category=Category.DIS_SYNERGY,
        rationale="r",
        estimated_value=EstimatedValue(low=-16_000_000, base=-12_000_000, high=-8_000_000),
        implementation_difficulty=Difficulty.LOW,
        time_horizon="0-6 months",
        calculation_method="calculate_dis_synergy_scenario",
        calculation_inputs={
            "baseline_revenue": 800_000_000,
            "attrition_pct_low": 0.01,
            "attrition_pct_base": 0.015,
            "attrition_pct_high": 0.02,
            "margin_pct": 1.0,
        },
    )


def test_uses_stated_low_high_as_bounds_for_a_base_parameter():
    rows = compute_tornado_rows([_cost_opportunity()])
    reduction_row = next(r for r in rows if r["parameter"] == "reduction_pct_base")
    # baseline_cost * reduction_pct_low/high, exactly what the opportunity itself states
    assert reduction_row["total_low"] == pytest.approx(150_000_000)
    assert reduction_row["total_high"] == pytest.approx(300_000_000)


def test_low_high_parameters_are_not_rows_of_their_own():
    rows = compute_tornado_rows([_cost_opportunity()])
    params = {r["parameter"] for r in rows}
    assert "reduction_pct_low" not in params
    assert "reduction_pct_high" not in params


def test_baseline_swings_plus_minus_twenty_percent():
    rows = compute_tornado_rows([_cost_opportunity()])
    baseline_row = next(r for r in rows if r["parameter"] == "baseline_cost")
    # 1.2B * 0.15 and 1.8B * 0.15
    assert baseline_row["total_low"] == pytest.approx(1_200_000_000 * 0.15)
    assert baseline_row["total_high"] == pytest.approx(1_800_000_000 * 0.15)


def test_percentage_swing_is_clamped_to_one():
    rows = compute_tornado_rows([_revenue_opportunity()])
    margin_row = next(r for r in rows if r["parameter"] == "incremental_margin_pct")
    # incremental_margin_pct=1.0 can't swing above 1.0
    assert margin_row["total_high"] == pytest.approx(12_000_000 / 1.0 * 1.0)
    assert margin_row["total_low"] < margin_row["total_high"]


def test_rows_are_sorted_by_swing_descending():
    rows = compute_tornado_rows([_cost_opportunity(), _revenue_opportunity()])
    swings = [r["swing"] for r in rows]
    assert swings == sorted(swings, reverse=True)


def test_total_bounds_reflect_the_other_opportunity_held_at_base():
    opportunities = [_cost_opportunity(), _revenue_opportunity()]
    total_base = sum(o.estimated_value.base for o in opportunities)
    rows = compute_tornado_rows(opportunities)
    reduction_row = next(r for r in rows if r["parameter"] == "reduction_pct_base")
    # total swing = cost opportunity's own swing, revenue opportunity held fixed at its base
    assert reduction_row["total_low"] == pytest.approx(total_base - 225_000_000 + 150_000_000)
    assert reduction_row["total_high"] == pytest.approx(total_base - 225_000_000 + 300_000_000)


def test_empty_opportunities_returns_empty_rows():
    assert compute_tornado_rows([]) == []


def test_opportunity_without_calculation_inputs_is_skipped():
    o = _cost_opportunity()
    o.calculation_inputs = {}
    assert compute_tornado_rows([o]) == []


def test_scenario_total_downside_is_below_base_and_upside_above():
    opportunities = [_cost_opportunity(), _revenue_opportunity()]
    total_base = sum(o.estimated_value.base for o in opportunities)
    downside = compute_scenario_total(opportunities, "low")
    upside = compute_scenario_total(opportunities, "high")
    assert downside < total_base < upside


def test_scenario_total_downside_matches_every_param_at_its_low_bound():
    # cost opp: baseline_cost -20%, reduction_pct_base -> its own stated low (0.10)
    # revenue opp: baseline_revenue -20%, uplift_pct_base -> 0.01, incremental_margin_pct -20% (clamped >=0)
    opportunities = [_cost_opportunity(), _revenue_opportunity()]
    downside = compute_scenario_total(opportunities, "low")
    expected_cost = (1_500_000_000 * 0.8) * 0.10
    expected_revenue = (800_000_000 * 0.8) * 0.01 * 0.8
    assert downside == pytest.approx(expected_cost + expected_revenue)


def test_scenario_total_rejects_bad_direction():
    with pytest.raises(ValueError):
        compute_scenario_total([_cost_opportunity()], "sideways")


def test_scenario_total_empty_opportunities_is_zero():
    assert compute_scenario_total([], "low") == 0.0


def test_scenario_total_downside_stresses_a_dis_synergy_toward_more_harm_not_less():
    """A dis-synergy's 'low'-suffixed input (attrition_pct_low) is the LEAST harmful case, the
    opposite of a benefit parameter's '_low' meaning 'worst'. The combined downside scenario
    must still pick whichever bound actually makes the total worse (more attrition here), not
    blindly substitute the parameter literally named '_low'.
    """
    opportunities = [_dis_synergy_opportunity()]
    total_base = sum(o.estimated_value.base for o in opportunities)
    downside = compute_scenario_total(opportunities, "low")
    upside = compute_scenario_total(opportunities, "high")
    assert downside < total_base < upside


def test_tornado_swing_direction_agnostic_for_dis_synergy():
    rows = compute_tornado_rows([_dis_synergy_opportunity()])
    attrition_row = next(r for r in rows if r["parameter"] == "attrition_pct_base")
    assert attrition_row["total_low"] == pytest.approx(-16_000_000)
    assert attrition_row["total_high"] == pytest.approx(-8_000_000)
