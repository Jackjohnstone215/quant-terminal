"""Unit tests for the valuation & scoring math.

Run directly (no pytest needed):   .venv/Scripts/python.exe test_valuation.py
Or with pytest if installed:       .venv/Scripts/python.exe -m pytest test_valuation.py -q

These test the PURE MATH — no network, no Streamlit state. They exist because every
valuation bug found so far (sign-flipped net debt, 100x DDM, lookahead backtest,
negative-FCF scoring) was caught by ad-hoc audits *after* shipping; these catch the
same class of error at write time.
"""
import math

from valuation import (
    RISK_FREE_RATE, EQUITY_RISK_PREMIUM,
    capm_rate, dcf_from_params, dcf_3stage, sustainable_growth,
    reverse_dcf_growth, wacc, fcff_wacc_value, monte_carlo_dcf,
    _rate_anchored_multiple, estimate_fair_value, safe_float, norm_yield_pct,
    clamp, safe_score, sharpe_ratio, fund_trend_score,
)


def close(a, b, tol=1e-3):
    return a is not None and b is not None and abs(a - b) <= tol


# ---------- CAPM discount rate ----------

def test_capm_default_beta():
    # beta None -> 1.0 -> rf + ERP
    assert close(capm_rate(None), RISK_FREE_RATE + EQUITY_RISK_PREMIUM)


def test_capm_clamps():
    assert close(capm_rate(0.1), 0.075)   # low-beta floor
    assert close(capm_rate(5.0), 0.14)    # high-beta ceiling
    assert capm_rate(0.5) < capm_rate(1.0) < capm_rate(2.0)


# ---------- DCF family ----------

def test_dcf_2stage_hand_computed():
    # fcf=1, no growth, r=10%, terminal g=2.5%, 5 yrs:
    # annuity PV 3.790787 + terminal (1.025/0.075)/1.1^5 = 8.485920 -> 12.276707
    assert close(dcf_from_params(1.0, 0.0, 0.10, 0.025, 5), 12.2767, tol=1e-3)


def test_dcf_invalid_inputs_return_none():
    assert dcf_from_params(None, 0.05, 0.10) is None
    assert dcf_from_params(-1.0, 0.05, 0.10) is None
    assert dcf_from_params(1.0, 0.05, 0.02, g_term=0.025) is None   # r <= g_term
    assert dcf_3stage(0.0, 0.05, 0.10) is None
    assert dcf_3stage(1.0, 0.05, 0.02, g_term=0.025) is None


def test_dcf_3stage_monotonic_in_growth():
    lo = dcf_3stage(1.0, 0.02, 0.10)
    hi = dcf_3stage(1.0, 0.12, 0.10)
    assert lo is not None and hi is not None and hi > lo


def test_dcf_3stage_monotonic_in_discount_rate():
    cheap_money = dcf_3stage(1.0, 0.05, 0.08)
    dear_money = dcf_3stage(1.0, 0.05, 0.13)
    assert cheap_money > dear_money


# ---------- Sustainable growth (total-payout aware) ----------

def test_sustainable_growth_basic():
    assert close(sustainable_growth(0.20, 0.25), 0.15)


def test_sustainable_growth_over_100pct_payout_goes_negative():
    # A firm returning more than it earns (AAPL-style total payout) cannot self-fund growth.
    assert close(sustainable_growth(0.30, 1.10), -0.03)


def test_sustainable_growth_payout_clamped_at_150pct():
    assert close(sustainable_growth(0.30, 5.0), 0.30 * (1 - 1.5))


def test_sustainable_growth_no_roe():
    assert sustainable_growth(None, 0.5) is None


# ---------- Reverse DCF ----------

def test_reverse_dcf_roundtrip():
    # Price a stock with 10% growth, then recover ~10% from that price.
    r_beta = 1.0
    price = dcf_3stage(1.0, 0.10, capm_rate(r_beta))
    implied = reverse_dcf_growth(price, 1.0, r_beta)
    assert close(implied, 0.10, tol=0.005)


def test_reverse_dcf_unjustifiable_price():
    assert reverse_dcf_growth(1e9, 1.0, 1.0) is None      # even 50% growth can't get there
    assert reverse_dcf_growth(100.0, -1.0, 1.0) is None   # negative FCF


# ---------- WACC / FCFF ----------

def test_wacc_no_debt_equals_cost_of_equity():
    assert close(wacc(1.0, 100e9, 0.0, 0.0), capm_rate(1.0))


def test_wacc_with_debt_below_cost_of_equity():
    w = wacc(1.0, 50e9, 50e9, 2.0)
    assert w is not None and 0.04 < w < capm_rate(1.0)    # debt tax shield lowers it


def test_wacc_invalid_equity():
    assert wacc(1.0, 0, 10e9, 1.0) is None


def test_fcff_wacc_value_positive_for_sane_inputs():
    v = fcff_wacc_value(fcf_ps=5.0, price=100.0, market_cap=50e9, total_debt=30e9,
                        total_cash=5e9, beta=1.0, net_debt_to_ebitda=2.5, growth_rate=0.06)
    assert v is not None and v > 0


def test_fcff_wacc_value_rejects_bad_inputs():
    assert fcff_wacc_value(-1.0, 100.0, 50e9, 1e9, 1e9, 1.0, 2.0, 0.05) is None
    assert fcff_wacc_value(5.0, None, 50e9, 1e9, 1e9, 1.0, 2.0, 0.05) is None


# ---------- Monte Carlo ----------

def test_monte_carlo_deterministic_per_seed():
    a = monte_carlo_dcf(5.0, 0.08, 1.0, n=500, seed=42)
    b = monte_carlo_dcf(5.0, 0.08, 1.0, n=500, seed=42)
    assert a is not None and b is not None
    assert len(a) == len(b) and all(x == y for x, y in zip(a, b))


def test_monte_carlo_rejects_negative_fcf():
    assert monte_carlo_dcf(-2.0, 0.08, 1.0) is None


# ---------- Rate-anchored fallback multiple ----------

def test_rate_anchored_multiple():
    r = capm_rate(1.0)
    g = min(0.025, RISK_FREE_RATE)
    assert close(_rate_anchored_multiple(1.0), 1.0 / (r - g))


# ---------- estimate_fair_value (un-anchored v2) ----------

def _fv(**kw):
    base = dict(price=100.0, pe=None, fcf_ps=None, ev_to_fcf=None, growth_rate=0.05,
                beta=1.0, dividend_yield=None, roe=None, payout=None, sector="Technology",
                price_to_book=None, market_cap=50e9, total_debt=1e9, total_cash=5e9,
                net_debt_to_ebitda=-0.2)
    base.update(kw)
    return estimate_fair_value(**base)


def test_fv_no_price():
    r = _fv(price=None)
    assert r["central"] is None and r["n_methods"] == 0


def test_fv_unanchored_can_sit_far_below_price():
    # 100x earnings vs a 10x sector: the OLD engine's 0.4x-price floor made this
    # invisible. The whole point of v2 is that this reads as massively overvalued.
    r = _fv(pe=100.0, fcf_ps=0.5, ev_to_fcf=200.0, sector_pe=10.0, sector_ev_fcf=10.0)
    assert r["n_methods"] >= 3
    assert r["n_above"] == 0
    assert r["central"] < 0.4 * 100.0          # below where the old cap would have stopped
    assert all(v > 0 for _, v in r["methods"])


def test_fv_no_price_anchored_pseudo_methods():
    r = _fv(pe=20.0, fcf_ps=4.0, ev_to_fcf=22.0, sector_pe=18.0, sector_ev_fcf=16.0)
    names = " ".join(n for n, _ in r["methods"])
    assert "52-week" not in names and "PEG" not in names


def test_fv_ddm_only_for_meaningful_payers():
    token = _fv(pe=20.0, dividend_yield=0.004)   # 0.4% token payer
    real = _fv(pe=20.0, dividend_yield=0.03)     # 3% real payer
    assert not any("DDM" in n for n, _ in token["methods"])
    assert any("DDM" in n for n, _ in real["methods"])


def test_fv_financials_use_justified_pb_not_cashflow():
    r = _fv(sector="Financial Services", pe=11.0, fcf_ps=5.0, ev_to_fcf=8.0,
            price_to_book=1.4, roe=0.13, payout=0.55, sector_pe=12.0)
    names = " ".join(n for n, _ in r["methods"])
    assert "P/B (justified)" in names
    assert "EV/FCF" not in names and "DCF" not in names


def test_fv_votes_count_methods_above_price():
    r = _fv(pe=6.0, fcf_ps=8.0, ev_to_fcf=5.0, sector_pe=12.0, sector_ev_fcf=10.0)
    above = sum(1 for _, v in r["methods"] if v > 100.0)
    assert r["n_above"] == above and r["n_methods"] == len(r["methods"])


def test_fv_single_method_is_low_confidence():
    r = _fv(pe=20.0, sector_pe=25.0)    # nothing else available -> one method
    assert r["n_methods"] == 1 and r["confidence"] == "Low"


def test_fv_sector_multiple_labels():
    r = _fv(pe=20.0, sector_pe=25.0)
    assert "sector median" in r["methods"][0][0]
    r2 = _fv(pe=20.0)                   # no sector data -> rate-anchored fallback
    assert "rate-anchored" in r2["methods"][0][0]


# ---------- small helpers ----------

def test_safe_float():
    assert safe_float("3.5") == 3.5
    assert safe_float(None) is None
    assert safe_float("abc", 7.0) == 7.0
    assert safe_float(float("nan")) is None


def test_norm_yield_pct():
    assert close(norm_yield_pct(0.0234), 2.34)   # fraction -> percent
    assert close(norm_yield_pct(6.45), 6.45)     # already percent


# ---------- scoring primitives (clamp, safe_score) ----------

def test_clamp_bounds_and_default():
    assert clamp(150) == 100 and clamp(-20) == 0 and clamp(63) == 63
    assert clamp(None) == 50            # missing -> neutral, not 0
    assert clamp(1.5, 0, 1) == 1.0


def test_safe_score_missing_is_neutral():
    # Missing data must NOT read as a perfect or terrible score — it's a neutral 50.
    assert safe_score(None, 0.05, 0.20) == 50.0


def test_safe_score_linear_and_bounds():
    assert safe_score(0.05, 0.05, 0.25) == 0.0        # at/below floor
    assert safe_score(0.25, 0.05, 0.25) == 100.0      # at/above ceiling
    assert close(safe_score(0.15, 0.05, 0.25), 50.0)  # midpoint
    assert safe_score(0.30, 0.05, 0.25) == 100.0      # clamps above ceiling


def test_safe_score_reverse_lower_is_better():
    # For P/E-like metrics, lower scores higher.
    assert safe_score(8, 8, 40, reverse=True) == 100.0
    assert safe_score(40, 8, 40, reverse=True) == 0.0
    assert safe_score(24, 8, 40, reverse=True) == 50.0
    # Monotonically decreasing as the metric worsens.
    assert safe_score(12, 8, 40, reverse=True) > safe_score(30, 8, 40, reverse=True)


def test_safe_score_negative_multiple_maps_to_worst_when_caller_sentinels():
    # A negative EV/FCF is numerically "cheapest" but really the worst; the engine maps such
    # values to a large sentinel BEFORE scoring. Confirm the sentinel then scores 0 (reverse).
    sentinel = 999
    assert safe_score(sentinel, 8, 40, reverse=True) == 0.0


# ---------- fund / multi-asset scoring (Sharpe, trend score) ----------

def test_sharpe_ratio_basic():
    # 12% return, 10% vol, 4.3% risk-free -> (12-4.3)/10 = 0.77
    assert close(sharpe_ratio(12.0, 10.0, 4.3), 0.77, tol=0.01)


def test_sharpe_ratio_rewards_lower_risk():
    # Same return, less volatility -> higher Sharpe.
    assert sharpe_ratio(8.0, 8.0) > sharpe_ratio(8.0, 20.0)


def test_sharpe_ratio_missing_or_zero_vol():
    assert sharpe_ratio(10.0, 0) is None
    assert sharpe_ratio(None, 10.0) is None


def test_fund_trend_score_uptrend_beats_downtrend():
    up = fund_trend_score(ret_3m=6, ret_6m=12, ret_1y=22, volatility=14, max_drawdown=-9, expense=0.03)
    down = fund_trend_score(ret_3m=-6, ret_6m=-12, ret_1y=-18, volatility=30, max_drawdown=-35, expense=0.03)
    assert 0 <= down < up <= 100
    assert up >= 70 and down <= 35


def test_fund_trend_score_penalizes_risk_for_same_return():
    calm = fund_trend_score(ret_3m=4, ret_6m=8, ret_1y=15, volatility=8, max_drawdown=-6)
    wild = fund_trend_score(ret_3m=4, ret_6m=8, ret_1y=15, volatility=35, max_drawdown=-30)
    assert calm > wild        # same trend, more risk -> lower score


def test_fund_trend_score_missing_data_is_neutralish():
    # All-missing shouldn't peg to 0 or 100 — safe_score neutralizes to ~50.
    s = fund_trend_score(None, None, None, None, None, None)
    assert 40 <= s <= 60


if __name__ == "__main__":
    import sys, traceback
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
