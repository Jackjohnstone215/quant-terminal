"""Pure valuation math for the quant terminal — no Streamlit, no network, no file I/O.

Everything here is deterministic given its inputs, which is what makes it unit-testable
(see test_valuation.py). dashboard.py imports from this module and re-exports the names,
so run_scan.py / audit.py / existing code keep working unchanged.

Methodology notes live on each function; the guiding sources are Damodaran (sustainable
growth, justified multiples, FCFF/WACC) and standard CFA curriculum treatments.
"""
import math

import pandas as pd

RISK_FREE_RATE = 0.043     # ~10-yr Treasury
EQUITY_RISK_PREMIUM = 0.05  # long-run equity premium over risk-free


def safe_float(value, default=None):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def norm_yield_pct(value):
    """Normalize a dividend yield to a true percent, robust to the source's unit convention.
    FMP returns dividendYield as a PERCENT (6.45) while other ratios are fractions (0.30) — so a
    blind ×100 gives 645%. Rule: interpret as a fraction (×100); if that implies an absurd yield
    (>25%), it was already a percent, so use it as-is. Handles both fraction and percent inputs."""
    value = safe_float(value)
    if value is None:
        return None
    as_pct = value * 100
    return round(value, 2) if as_pct > 25 else round(as_pct, 2)


def clamp(value, low=0, high=100):
    """Pin a value into [low, high]; non-numeric input falls back to a neutral 50 first."""
    value = safe_float(value, 50)
    return max(low, min(high, value))


def safe_score(value, good_low, good_high, reverse=False):
    """Map a raw metric to a 0-100 score by linear interpolation between good_low and good_high.
    Missing data returns a neutral 50 (never a false 0 or 100). `reverse=True` for metrics where
    LOWER is better (P/E, leverage): good_low scores 100, good_high scores 0. Callers that must
    penalize a nonsensical input (e.g. a NEGATIVE EV/FCF, which is 'cheapest' numerically but
    actually worst) map it to the bad end BEFORE calling — this function only interpolates."""
    value = safe_float(value)
    if value is None:
        return 50.0
    if reverse:
        if value <= good_low:
            return 100.0
        if value >= good_high:
            return 0.0
        return round(100 - ((value - good_low) / (good_high - good_low)) * 100, 1)
    if value <= good_low:
        return 0.0
    if value >= good_high:
        return 100.0
    return round(((value - good_low) / (good_high - good_low)) * 100, 1)


def capm_rate(beta):
    """Discount rate from CAPM: risk_free + beta × equity-risk-premium, clamped to a sane
    band. A high-beta stock is discounted harder (worth less), a defensive one less so —
    far more principled than a fixed rate."""
    b = safe_float(beta, 1.0)
    if b is None:
        b = 1.0
    b = max(0.5, min(2.2, b))
    return max(0.075, min(0.14, RISK_FREE_RATE + b * EQUITY_RISK_PREMIUM))


def dcf_from_params(fcf_ps, g1, r, g_term=0.025, years=5):
    """Simple 2-stage DCF (used by the interactive Valuation Lab)."""
    fcf_ps = safe_float(fcf_ps)
    if fcf_ps is None or fcf_ps <= 0 or r is None or g_term is None or r <= g_term:
        return None
    pv, cf = 0.0, fcf_ps
    for yr in range(1, years + 1):
        cf *= (1 + g1)
        pv += cf / ((1 + r) ** yr)
    terminal = cf * (1 + g_term) / (r - g_term)
    pv += terminal / ((1 + r) ** years)
    return pv


def dcf_3stage(fcf_ps, g_high, r, g_term=0.025, high_years=5, fade_years=5):
    """3-stage DCF: `high_years` at g_high, then a linear fade to g_term over `fade_years`,
    then a Gordon-growth terminal — the realistic shape (few firms grow fast forever)."""
    fcf_ps = safe_float(fcf_ps)
    if fcf_ps is None or fcf_ps <= 0 or r is None or r <= g_term:
        return None
    pv, cf, yr = 0.0, fcf_ps, 0
    for _ in range(high_years):
        yr += 1
        cf *= (1 + g_high)
        pv += cf / ((1 + r) ** yr)
    for i in range(1, fade_years + 1):
        g = g_high + (g_term - g_high) * (i / fade_years)
        yr += 1
        cf *= (1 + g)
        pv += cf / ((1 + r) ** yr)
    terminal = cf * (1 + g_term) / (r - g_term)
    pv += terminal / ((1 + r) ** yr)
    return pv


def sustainable_growth(roe, payout):
    """Fundamental (self-funded) growth = retention × ROE = (1 − payout) × ROE. Damodaran's
    core discipline: a firm can't grow faster than its reinvestment and returns allow.

    `payout` should be the TOTAL shareholder payout (dividends + net buybacks) / net income,
    not the dividend-only ratio — a firm returning 90% of earnings via buybacks retains
    almost nothing to reinvest, even if its dividend payout reads 0%. Total payout above
    100% (returning more than it earns) is allowed and yields negative retention → negative
    sustainable growth, which is the honest read. roe/payout are fractions. None if no ROE."""
    roe = safe_float(roe)
    if roe is None:
        return None
    payout = safe_float(payout, 0.0)
    payout = min(max(payout if payout is not None else 0.0, 0.0), 1.5)
    return roe * (1 - payout)


def _dcf_fair_value(fcf_ps, growth_rate, beta=None, roe=None, payout=None):
    """Engine DCF: CAPM discount rate + 3-stage growth, with stage-1 growth ANCHORED to
    sustainable growth (retention × ROE) so we never assume more growth than the business
    can fund. Terminal growth capped at the risk-free rate. None if no positive FCF."""
    observed = max(safe_float(growth_rate, 0.05) or 0.05, 0.0)
    sg = sustainable_growth(roe, payout)
    if sg is not None:
        # take the more conservative of observed vs fundable (allow a small near-term buffer)
        g1 = min(observed, max(sg, 0.0) + 0.03)
    else:
        g1 = observed
    g1 = min(max(g1, 0.0), 0.16)
    g_term = min(0.025, RISK_FREE_RATE)   # can't outgrow the economy forever
    return dcf_3stage(fcf_ps, g1, capm_rate(beta), g_term=g_term)


def reverse_dcf_growth(price, fcf_ps, beta):
    """Solve for the stage-1 FCF growth rate the CURRENT PRICE implies (3-stage DCF, CAPM
    rate). Answers 'what does the market expect?' — compare it to reality to judge the price."""
    price, fcf_ps = safe_float(price), safe_float(fcf_ps)
    if not price or not fcf_ps or fcf_ps <= 0:
        return None
    r = capm_rate(beta)
    lo, hi = -0.10, 0.50
    if dcf_3stage(fcf_ps, hi, r) < price:   # even 50% growth can't justify it
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        v = dcf_3stage(fcf_ps, mid, r)
        if v is None:
            return None
        if v < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _cost_of_debt(net_debt_to_ebitda):
    """Pre-tax cost of debt ≈ risk-free + a credit spread that widens with leverage."""
    spread = min(max(0.010 + (safe_float(net_debt_to_ebitda, 1.0) or 1.0) * 0.006, 0.010), 0.06)
    return RISK_FREE_RATE + spread


def wacc(beta, market_cap, total_debt, net_debt_to_ebitda, tax=0.21):
    """Weighted-average cost of capital: blends cost of equity (CAPM) and after-tax cost of
    debt by capital-structure weights. Lower than cost of equity for levered firms — which
    correctly raises their intrinsic value (the debt tax shield)."""
    E = safe_float(market_cap)
    if not E or E <= 0:
        return None
    D = max(safe_float(total_debt, 0.0) or 0.0, 0.0)
    V = E + D
    re, rd = capm_rate(beta), _cost_of_debt(net_debt_to_ebitda)
    return (E / V) * re + (D / V) * rd * (1 - tax)


def fcff_wacc_value(fcf_ps, price, market_cap, total_debt, total_cash, beta,
                    net_debt_to_ebitda, growth_rate, roe=None, payout=None, tax=0.21):
    """Enterprise DCF: value FCFF (free cash flow to the FIRM) at WACC → enterprise value →
    subtract net debt → equity value per share. The right approach for heavily-levered
    non-financials, where cost-of-equity FCFE DCF understates the value of cheap debt."""
    fcf_ps, price, mc = safe_float(fcf_ps), safe_float(price), safe_float(market_cap)
    if not fcf_ps or fcf_ps <= 0 or not price or not mc or mc <= 0:
        return None
    shares = mc / price
    td = max(safe_float(total_debt, 0.0) or 0.0, 0.0)
    tc = max(safe_float(total_cash, 0.0) or 0.0, 0.0)
    # FCFF ≈ FCFE + after-tax interest (add back cash paid to debt holders)
    fcfe_total = fcf_ps * shares
    fcff_total = fcfe_total + td * _cost_of_debt(net_debt_to_ebitda) * (1 - tax)
    w = wacc(beta, mc, td, net_debt_to_ebitda, tax)
    if w is None or w <= 0.025:
        return None
    observed = max(safe_float(growth_rate, 0.05) or 0.05, 0.0)
    sg = sustainable_growth(roe, payout)
    g1 = min(observed, max(sg, 0.0) + 0.03) if sg is not None else observed
    g1 = min(max(g1, 0.0), 0.16)
    ev_ps = dcf_3stage(fcff_total / shares, g1, w, g_term=min(0.025, RISK_FREE_RATE))
    if ev_ps is None:
        return None
    equity_value = ev_ps * shares - (td - tc)   # EV − net debt = equity value
    return equity_value / shares if shares else None


def monte_carlo_dcf(fcf_ps, base_growth, beta, n=3000, seed=0):
    """Run N DCF simulations with randomized assumptions (growth, discount rate, terminal
    rate, starting FCF) to get a DISTRIBUTION of fair value instead of a point estimate.
    Returns the array of simulated per-share values (deterministic per seed)."""
    import numpy as np
    fcf_ps = safe_float(fcf_ps)
    if not fcf_ps or fcf_ps <= 0:
        return None
    rng = np.random.default_rng(seed)
    base_r = capm_rate(beta)
    g = np.clip(rng.normal(base_growth, 0.045, n), -0.05, 0.30)      # growth uncertainty
    r = np.clip(rng.normal(base_r, 0.015, n), 0.06, 0.16)           # discount-rate uncertainty
    gt = np.clip(rng.normal(0.023, 0.005, n), 0.005, RISK_FREE_RATE)  # terminal-growth uncertainty
    fmult = np.clip(rng.normal(1.0, 0.10, n), 0.7, 1.35)            # starting-FCF uncertainty
    vals = []
    for i in range(n):
        v = dcf_3stage(fcf_ps * fmult[i], float(g[i]), float(r[i]), g_term=float(gt[i]))
        if v is not None and v > 0:
            vals.append(v)
    return np.array(vals) if len(vals) > 100 else None


def _rate_anchored_multiple(beta):
    """Fallback fair multiple when sector data is thin: value $1 of earnings/FCF as a
    perpetuity growing at the terminal rate, discounted at CAPM — 1/(r − g). Moves with
    the rate environment (rates up → fair multiple down), unlike a hardcoded number."""
    r = capm_rate(beta)
    g = min(0.025, RISK_FREE_RATE)
    return 1.0 / (r - g) if r > g else None


def estimate_fair_value(price, pe, fcf_ps, ev_to_fcf, growth_rate,
                        beta=None, dividend_yield=None, roe=None, payout=None,
                        sector=None, price_to_book=None, market_cap=None, total_debt=None,
                        total_cash=None, net_debt_to_ebitda=None,
                        sector_pe=None, sector_ev_fcf=None):
    """Blend independent valuation methods into an honest verdict — WITHOUT anchoring to
    the current price.

    v2 (un-anchored). The old version capped every method to [0.4x, 2.5x] of the current
    price and voted in a 52-week-midpoint 'method' — which guaranteed fair value always
    looked reasonable next to the price and made extreme mispricing structurally invisible.
    Now: no price caps, no price-history pseudo-methods, no PEG (redundant with P/E +
    growth, and the main source of exploding outputs), and no score-conditioned multiples
    (quality is scored elsewhere; baking it into fair value double-counted it). Multiples
    come from the stock's own sector (median P/E and EV/FCF from the latest scan), falling
    back to a rate-anchored perpetuity multiple. Financials get justified P/B instead of
    cash-flow methods.

    Instead of pretending to a precise target, the result carries a verdict layer:
    n_above/n_methods = how many methods value the stock ABOVE today's price (the votes),
    and a confidence grade from how tightly the methods agree. central/low/high are the
    median and full range of the (uncapped) methods."""
    price = safe_float(price)
    if not price or price <= 0:
        return {"central": None, "low": None, "high": None, "methods": [],
                "n_above": 0, "n_methods": 0, "confidence": None}
    is_financial = bool(sector) and any(k in str(sector).lower() for k in ["financ", "bank", "insur"])
    methods = []

    pe = safe_float(pe)
    if pe and pe > 0:
        eps = price / pe
        fair_pe = safe_float(sector_pe)
        if fair_pe and fair_pe > 0:
            methods.append((f"P/E (sector median {fair_pe:.0f}x)", eps * fair_pe))
        else:
            fair_pe = _rate_anchored_multiple(beta)
            if fair_pe:
                methods.append((f"P/E (rate-anchored {fair_pe:.0f}x)", eps * fair_pe))

    if not is_financial:
        ev_to_fcf = safe_float(ev_to_fcf)
        if ev_to_fcf and ev_to_fcf > 0:
            fair_ev_fcf = safe_float(sector_ev_fcf)
            label = "EV/FCF (sector median {:.0f}x)"
            if not (fair_ev_fcf and fair_ev_fcf > 0):
                fair_ev_fcf = _rate_anchored_multiple(beta)
                label = "EV/FCF (rate-anchored {:.0f}x)"
            if fair_ev_fcf:
                methods.append((label.format(fair_ev_fcf), price * (fair_ev_fcf / ev_to_fcf)))

        # Heavily-levered non-financials → FCFF discounted at WACC (captures the debt tax
        # shield). Lightly-levered → the simpler FCFE / cost-of-equity DCF.
        ndte = safe_float(net_debt_to_ebitda)
        if ndte is not None and ndte > 1.5:
            dcf = fcff_wacc_value(fcf_ps, price, market_cap, total_debt, total_cash, beta,
                                  ndte, growth_rate, roe, payout)
            if dcf:
                methods.append(("DCF (FCFF/WACC)", dcf))
        else:
            dcf = _dcf_fair_value(fcf_ps, growth_rate, beta, roe, payout)
            if dcf:
                methods.append(("DCF (3-stage, CAPM)", dcf))
    else:
        # Financials: justified P/B = (ROE − g)/(r − g), applied to book value per share.
        ptb = safe_float(price_to_book)
        roe_f = safe_float(roe)
        if ptb and ptb > 0 and roe_f is not None:
            book_ps = price / ptb
            r = capm_rate(beta)
            g = min(max(sustainable_growth(roe, payout) or 0.02, 0.0), r - 0.005)
            fair_pb = (roe_f - g) / (r - g) if (r > g and roe_f > g) else (roe_f / r if r else 1.0)
            fair_pb = min(max(fair_pb, 0.3), 5.0)
            methods.append(("P/B (justified)", fair_pb * book_ps))

    # Dividend Discount Model (Gordon growth) — only for MEANINGFUL payers (yield ≥ 1.5%).
    # For a token payer (AAPL at ~0.4%) the dividend isn't the return vehicle, and DDM
    # produces an absurdly low value that pollutes the votes and the confidence grade.
    # Normalize the yield to a FRACTION first: the FMP path supplies it as a percent (6.45), and
    # dy*price below assumes a fraction — without this the "dividend" is ~100x too big and
    # inflates fair value for every payer.
    dyp = norm_yield_pct(dividend_yield)
    dy = (dyp / 100.0) if dyp is not None else None
    if dy and dy >= 0.015:
        r = capm_rate(beta)
        g = min(max(safe_float(growth_rate, 0.02) or 0.02, 0.0), r - 0.005, 0.08)
        if r > g:
            d1 = (dy * price) * (1 + g)
            methods.append(("Dividend (DDM)", d1 / (r - g)))

    # Sanity filter only (drop broken values, never clamp toward price — clamping fabricates).
    methods = [(n, v) for n, v in methods
               if safe_float(v) is not None and math.isfinite(v) and v > 0]
    if not methods:
        return {"central": None, "low": None, "high": None, "methods": [],
                "n_above": 0, "n_methods": 0, "confidence": None}

    vals = sorted(v for _, v in methods)
    m = len(vals)
    central = vals[m // 2] if m % 2 else (vals[m // 2 - 1] + vals[m // 2]) / 2
    n_above = sum(1 for v in vals if v > price)
    if m < 2:
        confidence = "Low"          # a single method is an opinion, not a consensus
    else:
        ratio = vals[-1] / vals[0]
        confidence = "High" if ratio <= 1.6 else ("Medium" if ratio <= 2.6 else "Low")
    return {"central": central, "low": vals[0], "high": vals[-1], "methods": methods,
            "n_above": n_above, "n_methods": m, "confidence": confidence}
