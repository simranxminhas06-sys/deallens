"""Deterministic financial calculations the agent can call as tools.

Every function is pure and independently testable (see tests/test_financial_calculator.py).
FUNCTION_SCHEMAS describes them in OpenAI Responses API function-calling format;
TOOL_FUNCTIONS maps each name to the callable the orchestrator invokes.
"""

from __future__ import annotations

import math


def calculate_growth_rate(beginning_value: float, ending_value: float, periods: float = 1) -> dict:
    """CAGR between two values over a number of periods (years)."""
    if beginning_value <= 0 or periods <= 0:
        raise ValueError("beginning_value and periods must be positive")
    rate = (ending_value / beginning_value) ** (1 / periods) - 1
    return {
        "growth_rate": round(rate, 6),
        "growth_rate_pct": round(rate * 100, 2),
        "method": "CAGR = (ending/beginning)^(1/periods) - 1",
    }


def calculate_margin(revenue: float, cost_or_profit: float, margin_type: str = "operating") -> dict:
    """margin_type='operating' treats cost_or_profit as operating income; 'gross' as gross profit."""
    if revenue == 0:
        raise ValueError("revenue must be non-zero")
    margin = cost_or_profit / revenue
    return {
        "margin": round(margin, 6),
        "margin_pct": round(margin * 100, 2),
        "margin_type": margin_type,
        "method": f"{margin_type}_margin = {margin_type}_income / revenue",
    }


def calculate_savings_scenario(
    baseline_cost: float,
    reduction_pct_low: float,
    reduction_pct_base: float,
    reduction_pct_high: float,
) -> dict:
    """Low/base/high annual cost-synergy value from a baseline cost base and reduction assumptions."""
    for pct, name in (
        (reduction_pct_low, "reduction_pct_low"),
        (reduction_pct_base, "reduction_pct_base"),
        (reduction_pct_high, "reduction_pct_high"),
    ):
        if not 0 <= pct <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    return {
        "low": round(baseline_cost * reduction_pct_low, 2),
        "base": round(baseline_cost * reduction_pct_base, 2),
        "high": round(baseline_cost * reduction_pct_high, 2),
        "baseline_cost": baseline_cost,
        "method": "savings = baseline_cost * reduction_pct",
    }


def calculate_revenue_scenario(
    baseline_revenue: float,
    uplift_pct_low: float,
    uplift_pct_base: float,
    uplift_pct_high: float,
    incremental_margin_pct: float = 1.0,
) -> dict:
    """Low/base/high incremental profit from a revenue base and cross-sell/uplift assumptions.

    incremental_margin_pct converts incremental revenue into incremental profit
    (use 1.0 to report the estimate in revenue terms instead of profit terms).
    """
    if not 0 <= incremental_margin_pct <= 1:
        raise ValueError("incremental_margin_pct must be between 0 and 1")
    values = {}
    for label, uplift in (("low", uplift_pct_low), ("base", uplift_pct_base), ("high", uplift_pct_high)):
        if uplift < 0:
            raise ValueError(f"uplift_pct_{label} must be non-negative")
        values[label] = round(baseline_revenue * uplift * incremental_margin_pct, 2)
    return {
        **values,
        "baseline_revenue": baseline_revenue,
        "incremental_margin_pct": incremental_margin_pct,
        "method": "value = baseline_revenue * uplift_pct * incremental_margin_pct",
    }


def calculate_dis_synergy_scenario(
    baseline_revenue: float,
    attrition_pct_low: float,
    attrition_pct_base: float,
    attrition_pct_high: float,
    margin_pct: float = 1.0,
) -> dict:
    """Low/base/high value DESTROYED by customer/revenue attrition following the deal — the
    downside counterpart to calculate_revenue_scenario that a rigorous synergy case nets
    against the upside, instead of only ever showing gains.

    attrition_pct_low/base/high are plain percentages (the smallest, most likely, and largest
    attrition rate an analyst would actually estimate — attrition_pct_low is the least attrition,
    attrition_pct_high the most). The returned dollars are negative, and — because more attrition
    is worse, the opposite of calculate_revenue_scenario's uplift_pct — the WORST case (computed
    from attrition_pct_high) is reported as 'low' and the BEST case (from attrition_pct_low) as
    'high', so 'low' <= 'base' <= 'high' still holds numerically like every other scenario here.
    """
    for pct, name in (
        (attrition_pct_low, "attrition_pct_low"),
        (attrition_pct_base, "attrition_pct_base"),
        (attrition_pct_high, "attrition_pct_high"),
    ):
        if not 0 <= pct <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if not 0 <= margin_pct <= 1:
        raise ValueError("margin_pct must be between 0 and 1")
    return {
        "low": -round(baseline_revenue * attrition_pct_high * margin_pct, 2),
        "base": -round(baseline_revenue * attrition_pct_base * margin_pct, 2),
        "high": -round(baseline_revenue * attrition_pct_low * margin_pct, 2),
        "baseline_revenue": baseline_revenue,
        "margin_pct": margin_pct,
        "method": "value_destroyed = -(baseline_revenue * attrition_pct * margin_pct); low uses attrition_pct_high (worst case), high uses attrition_pct_low (best case)",
    }


def calculate_combined_metric(acquirer_value: float, target_value: float, adjustment_pct: float = 0.0) -> dict:
    """Pro-forma combined metric (e.g. combined revenue) with an optional dis-synergy/synergy adjustment."""
    combined = (acquirer_value + target_value) * (1 + adjustment_pct)
    return {
        "combined_value": round(combined, 2),
        "pre_adjustment_sum": acquirer_value + target_value,
        "adjustment_pct": adjustment_pct,
        "method": "combined = (acquirer + target) * (1 + adjustment_pct)",
    }


def calculate_deal_economics(total_value_creation: float, deal_value: float) -> dict:
    """How the identified value creation compares to what was actually paid for the deal —
    not exposed to the LLM as a tool; used directly by the app to answer the question the
    rest of the pipeline never does: was this deal worth the price paid for it.
    """
    if deal_value <= 0:
        raise ValueError("deal_value must be positive")
    ratio = total_value_creation / deal_value
    return {
        "value_creation_pct_of_deal": round(ratio * 100, 2),
        "total_value_creation": round(total_value_creation, 2),
        "deal_value": deal_value,
        "method": "value_creation_pct_of_deal = total_value_creation / deal_value",
    }


def calculate_ramp_adjusted_value(
    base_value: float,
    year_1_pct: float,
    year_2_pct: float,
    year_3_pct: float,
    cost_to_achieve: float = 0.0,
) -> dict:
    """3-year cumulative value from a full-run-rate base value ramping in over three years,
    net of a one-time cost to capture it. Not exposed to the LLM as a tool.
    """
    for name, pct in (("year_1_pct", year_1_pct), ("year_2_pct", year_2_pct), ("year_3_pct", year_3_pct)):
        if pct < 0:
            raise ValueError(f"{name} must be non-negative")
    year_1 = round(base_value * year_1_pct, 2)
    year_2 = round(base_value * year_2_pct, 2)
    year_3 = round(base_value * year_3_pct, 2)
    cumulative = round(year_1 + year_2 + year_3, 2)
    net_of_cost = round(cumulative - cost_to_achieve, 2)
    return {
        "year_1": year_1,
        "year_2": year_2,
        "year_3": year_3,
        "cumulative_3yr": cumulative,
        "cost_to_achieve": cost_to_achieve,
        "net_3yr_value": net_of_cost,
        "method": "cumulative_3yr = base*(y1_pct+y2_pct+y3_pct); net_3yr_value = cumulative_3yr - cost_to_achieve",
    }


def calculate_accretion_dilution(
    deal_value: float,
    cash_pct: float,
    stock_pct: float,
    debt_pct: float,
    new_debt_interest_rate: float,
    foregone_interest_rate: float,
    acquirer_tax_rate: float,
    acquirer_share_price: float,
    acquirer_shares_outstanding: float,
    acquirer_net_income: float,
    target_net_income: float = 0.0,
    synergies_after_tax_run_rate: float = 0.0,
) -> dict:
    """EPS impact of financing deal_value with a cash/stock/debt mix. Not exposed to the LLM
    as a tool; used directly by the app, same as calculate_deal_economics.

    Reports pro forma EPS both before and after run-rate synergies, since Day 1 dilution
    funded by debt or stock is normal in real deals and isn't itself a red flag — what
    matters is whether synergies are expected to close the gap.
    """
    if deal_value <= 0:
        raise ValueError("deal_value must be positive")
    if acquirer_shares_outstanding <= 0 or acquirer_share_price <= 0:
        raise ValueError("acquirer_shares_outstanding and acquirer_share_price must be positive")
    if round(cash_pct + stock_pct + debt_pct, 6) != 1.0:
        raise ValueError("cash_pct + stock_pct + debt_pct must sum to 1.0")
    for pct, name in ((cash_pct, "cash_pct"), (stock_pct, "stock_pct"), (debt_pct, "debt_pct")):
        if not 0 <= pct <= 1:
            raise ValueError(f"{name} must be between 0 and 1")

    cash_used = deal_value * cash_pct
    new_debt = deal_value * debt_pct
    shares_issued = (deal_value * stock_pct) / acquirer_share_price
    pro_forma_shares = acquirer_shares_outstanding + shares_issued

    after_tax_interest_expense = new_debt * new_debt_interest_rate * (1 - acquirer_tax_rate)
    after_tax_foregone_interest = cash_used * foregone_interest_rate * (1 - acquirer_tax_rate)
    financing_drag = after_tax_interest_expense + after_tax_foregone_interest

    standalone_eps = acquirer_net_income / acquirer_shares_outstanding
    combined_net_income_day1 = acquirer_net_income + target_net_income - financing_drag
    pro_forma_eps_day1 = combined_net_income_day1 / pro_forma_shares
    combined_net_income_run_rate = combined_net_income_day1 + synergies_after_tax_run_rate
    pro_forma_eps_run_rate = combined_net_income_run_rate / pro_forma_shares

    def _pct_change(pro_forma: float) -> float:
        return (pro_forma - standalone_eps) / abs(standalone_eps)

    return {
        "cash_used": round(cash_used, 2),
        "new_debt": round(new_debt, 2),
        "shares_issued": round(shares_issued, 2),
        "pro_forma_shares": round(pro_forma_shares, 2),
        "after_tax_interest_expense": round(after_tax_interest_expense, 2),
        "after_tax_foregone_interest": round(after_tax_foregone_interest, 2),
        "standalone_eps": round(standalone_eps, 4),
        "pro_forma_eps_day1": round(pro_forma_eps_day1, 4),
        "pro_forma_eps_run_rate": round(pro_forma_eps_run_rate, 4),
        "accretion_dilution_pct_day1": round(_pct_change(pro_forma_eps_day1) * 100, 2),
        "accretion_dilution_pct_run_rate": round(_pct_change(pro_forma_eps_run_rate) * 100, 2),
        "method": (
            "pro_forma_eps = (acquirer_ni + target_ni - after_tax_financing_drag [+ after_tax_synergies]) "
            "/ (acquirer_shares + shares_issued_for_stock_pct)"
        ),
    }


def calculate_precision_flag(value: float, sig_figs_allowed: int = 3) -> dict:
    """Flags whether a dollar estimate is stated with implausible false precision."""
    if value == 0:
        return {"flagged": False, "reason": "zero value"}
    digits = len(str(int(abs(value))))
    non_zero_digits = len(str(int(abs(value))).rstrip("0"))
    flagged = non_zero_digits > sig_figs_allowed and digits > sig_figs_allowed
    return {
        "flagged": flagged,
        "digits": digits,
        "non_zero_trailing_digits": non_zero_digits,
        "reason": "estimate implies more precision than diligence-stage analysis supports" if flagged else "ok",
    }


FUNCTION_SCHEMAS = [
    {
        "type": "function",
        "name": "calculate_growth_rate",
        "description": "Compute CAGR between a beginning and ending value over N periods.",
        "parameters": {
            "type": "object",
            "properties": {
                "beginning_value": {"type": "number"},
                "ending_value": {"type": "number"},
                "periods": {"type": "number", "description": "Number of years between the two values"},
            },
            "required": ["beginning_value", "ending_value", "periods"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "calculate_margin",
        "description": "Compute a margin (operating or gross) as a fraction of revenue.",
        "parameters": {
            "type": "object",
            "properties": {
                "revenue": {"type": "number"},
                "cost_or_profit": {"type": "number"},
                "margin_type": {"type": "string", "enum": ["operating", "gross"]},
            },
            "required": ["revenue", "cost_or_profit", "margin_type"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "calculate_savings_scenario",
        "description": "Compute low/base/high annual cost-synergy value from a baseline cost and reduction assumptions.",
        "parameters": {
            "type": "object",
            "properties": {
                "baseline_cost": {"type": "number"},
                "reduction_pct_low": {"type": "number"},
                "reduction_pct_base": {"type": "number"},
                "reduction_pct_high": {"type": "number"},
            },
            "required": [
                "baseline_cost",
                "reduction_pct_low",
                "reduction_pct_base",
                "reduction_pct_high",
            ],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "calculate_revenue_scenario",
        "description": "Compute low/base/high incremental value from a revenue base and uplift assumptions.",
        "parameters": {
            "type": "object",
            "properties": {
                "baseline_revenue": {"type": "number"},
                "uplift_pct_low": {"type": "number"},
                "uplift_pct_base": {"type": "number"},
                "uplift_pct_high": {"type": "number"},
                "incremental_margin_pct": {"type": "number"},
            },
            "required": [
                "baseline_revenue",
                "uplift_pct_low",
                "uplift_pct_base",
                "uplift_pct_high",
                "incremental_margin_pct",
            ],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "calculate_combined_metric",
        "description": "Compute a pro-forma combined metric from acquirer and target values.",
        "parameters": {
            "type": "object",
            "properties": {
                "acquirer_value": {"type": "number"},
                "target_value": {"type": "number"},
                "adjustment_pct": {"type": "number"},
            },
            "required": ["acquirer_value", "target_value", "adjustment_pct"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "calculate_dis_synergy_scenario",
        "description": (
            "Compute low/base/high negative dollar value destroyed by customer/revenue attrition "
            "following the deal — the downside counterpart to calculate_revenue_scenario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "baseline_revenue": {"type": "number"},
                "attrition_pct_low": {"type": "number", "description": "Least-attrition case, 0-1"},
                "attrition_pct_base": {"type": "number", "description": "Most likely attrition case, 0-1"},
                "attrition_pct_high": {"type": "number", "description": "Worst-case attrition, 0-1"},
                "margin_pct": {"type": "number", "description": "Converts revenue at risk into profit at risk"},
            },
            "required": [
                "baseline_revenue",
                "attrition_pct_low",
                "attrition_pct_base",
                "attrition_pct_high",
                "margin_pct",
            ],
            "additionalProperties": False,
        },
    },
]

TOOL_FUNCTIONS = {
    "calculate_growth_rate": calculate_growth_rate,
    "calculate_margin": calculate_margin,
    "calculate_savings_scenario": calculate_savings_scenario,
    "calculate_revenue_scenario": calculate_revenue_scenario,
    "calculate_combined_metric": calculate_combined_metric,
    "calculate_dis_synergy_scenario": calculate_dis_synergy_scenario,
}
