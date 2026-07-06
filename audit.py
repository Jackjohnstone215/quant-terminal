"""Comprehensive accuracy audit.

For every stock in the watchlist, compares each statistic the app computes against FMP's
authoritative source-of-truth value, flagging any mismatch in value/scale/units. Writes a
dated report to ACCURACY_AUDIT.md and prints a summary. Requires FMP_API_KEY (else every
stock falls back to Yahoo and there's nothing to audit against FMP).

Run:  python audit.py
"""
import dashboard as d

TOL_OK = 0.02     # <=2% difference = accurate
TOL_SOFT = 0.10   # <=10% = minor (rounding/period differences)

# (app row field, function of (ratios, km, growth) -> truth value, tolerant?)
CHECKS = [
    ("P/E",               lambda r, k, g: r.get("priceToEarningsRatioTTM"), False),
    ("PEG",               lambda r, k, g: r.get("priceToEarningsGrowthRatioTTM"), False),
    ("P/S",               lambda r, k, g: r.get("priceToSalesRatioTTM"), False),
    ("EV/EBITDA",         lambda r, k, g: r.get("enterpriseValueMultipleTTM"), False),
    ("ROE %",             lambda r, k, g: _x100(k.get("returnOnEquityTTM")), False),
    ("ROA %",             lambda r, k, g: _x100(k.get("returnOnAssetsTTM")), False),
    ("ROIC Proxy %",      lambda r, k, g: _x100(k.get("returnOnInvestedCapitalTTM")), False),
    ("FCF Yield %",       lambda r, k, g: _x100(k.get("freeCashFlowYieldTTM")), False),
    ("Profit Margin %",   lambda r, k, g: _x100(r.get("netProfitMarginTTM")), False),
    ("Operating Margin %",lambda r, k, g: _x100(r.get("operatingProfitMarginTTM")), False),
    ("Gross Margin %",    lambda r, k, g: _x100(r.get("grossProfitMarginTTM")), False),
    ("EBITDA Margin %",   lambda r, k, g: _x100(r.get("ebitdaMarginTTM")), False),
    ("OCF Margin %",      lambda r, k, g: _x100(r.get("operatingCashFlowSalesRatioTTM")), False),
    ("FCF Conversion %",  lambda r, k, g: _x100(r.get("freeCashFlowOperatingCashFlowRatioTTM")), False),
    ("FCF Margin %",      lambda r, k, g: _fcf_margin(r), False),
    ("Net Debt/EBITDA",   lambda r, k, g: k.get("netDebtToEBITDATTM"), False),
    ("Debt/Equity",       lambda r, k, g: _x100(r.get("debtToEquityRatioTTM")), False),
    ("Current Ratio",     lambda r, k, g: r.get("currentRatioTTM"), False),
    ("Quick Ratio",       lambda r, k, g: r.get("quickRatioTTM"), False),
    ("Dividend Yield %",  lambda r, k, g: _x100(r.get("dividendYieldTTM")), False),
    ("Revenue Growth %",  lambda r, k, g: _x100(g.get("revenueGrowth")), True),   # period diff tolerated
]


def _x100(v):
    v = d.safe_float(v)
    return v * 100 if v is not None else None


def _fcf_margin(r):
    fcf, rev = d.safe_float(r.get("freeCashFlowPerShareTTM")), d.safe_float(r.get("revenuePerShareTTM"))
    return (fcf / rev * 100) if (fcf is not None and rev) else None


def classify(app_v, truth_v, tolerant):
    a, t = d.safe_float(app_v), d.safe_float(truth_v)
    if t is None:
        return "SKIP"
    if a is None:
        return "MISSING"
    rel = abs(a - t) / abs(t) if t else (0 if abs(a - t) < 1e-9 else 9)
    if rel <= TOL_OK:
        return "OK"
    if rel <= TOL_SOFT or tolerant:
        return "SOFT"
    return "DIFF"


def main():
    universe = list(dict.fromkeys(d.QUALITY_COMPOUNDERS + d.RECOVERY_WATCHLIST))
    tallies = {"OK": 0, "SOFT": 0, "DIFF": 0, "MISSING": 0, "SKIP": 0}
    diffs = []
    yahoo_fallback = []
    audited = 0

    for i, tkr in enumerate(universe, 1):
        try:
            row = d.get_quant_score(tkr)
        except Exception as e:
            diffs.append((tkr, "(scoring failed)", "", str(e)[:60]))
            continue
        if row.get("Data Source") != "FMP (SEC filings)":
            yahoo_fallback.append(tkr)   # FMP unavailable for this one — can't audit vs FMP
            continue
        ratios = d._fmp_get(f"ratios-ttm?symbol={tkr}") or {}
        km = d._fmp_get(f"key-metrics-ttm?symbol={tkr}") or {}
        growth = d._fmp_get(f"financial-growth?symbol={tkr}&period=annual&limit=1") or {}
        audited += 1
        for field, truth_fn, tolerant in CHECKS:
            verdict = classify(row.get(field), truth_fn(ratios, km, growth), tolerant)
            tallies[verdict] += 1
            if verdict in ("DIFF", "MISSING"):
                diffs.append((tkr, field, row.get(field), truth_fn(ratios, km, growth)))
        print(f"[{i}/{len(universe)}] {tkr} audited", flush=True)

    total = sum(v for k, v in tallies.items() if k != "SKIP")
    passed = tallies["OK"] + tallies["SOFT"]
    lines = [
        "# Accuracy Audit Report",
        "",
        f"- Stocks audited against FMP: **{audited}**",
        f"- Checks passed (exact or minor): **{passed}/{total}**  ({tallies['OK']} exact, {tallies['SOFT']} minor)",
        f"- **Mismatches (DIFF): {tallies['DIFF']}** · Missing: {tallies['MISSING']}",
        f"- Stocks that fell back to Yahoo (FMP unavailable, not audited): {len(yahoo_fallback)} {yahoo_fallback if yahoo_fallback else ''}",
        "",
    ]
    if diffs:
        lines += ["## Mismatches to investigate", "", "| Ticker | Field | App | Truth (FMP) |", "|---|---|---|---|"]
        for tkr, field, a, t in diffs:
            lines.append(f"| {tkr} | {field} | {a} | {t} |")
    else:
        lines.append("## No mismatches found — every audited statistic matches source-of-truth. ✅")

    report = "\n".join(lines)
    with open("ACCURACY_AUDIT.md", "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print("\n" + report)


if __name__ == "__main__":
    main()
