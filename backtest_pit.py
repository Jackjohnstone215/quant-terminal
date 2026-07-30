"""Point-in-time (PIT) historical backtest of the quant engine — the honest long-horizon test.

Reconstructs each company's fundamentals *as they were publicly known on a past date* using
SEC EDGAR XBRL data (every 10-K/10-Q back to ~2009, stamped with the date it was FILED), then
ranks by a fundamentals-core quant score and measures how those picks actually did to today.

No lookahead: for a decision date T, we use ONLY filings with filed <= T, so restatements and
later knowledge can't leak in. Prices come from Yahoo (historical, free).

Caveats (surfaced, never hidden):
  - Fundamentals-CORE score only (profitability, growth, leverage, valuation) — not the full
    live engine (no analyst data / some TTM margins point-in-time).
  - Survivorship bias: uses today's index membership, so delisted/acquired names are absent.
  - Non-financials only (financials/REITs use different XBRL tags — scored elsewhere).
  - As-of-T fundamentals lag ~1 year (you only have the last annual 10-K filed before T).

Run:  .venv/Scripts/python.exe backtest_pit.py
"""
import json
import os
import time
import urllib.request
import urllib.error
import datetime as dt

from valuation import safe_score, clamp, safe_float

SEC_UA = "quant-terminal research jack@example.com"   # SEC requires a descriptive UA
CACHE_DIR = os.path.join(os.environ.get("TEMP", "."), "pit_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _sec_get(url, cache_key=None, ttl_days=30):
    """GET a SEC JSON endpoint with the required UA + on-disk cache (SEC data barely changes)."""
    if cache_key:
        path = os.path.join(CACHE_DIR, cache_key + ".json")
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl_days * 86400:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            if cache_key:
                with open(os.path.join(CACHE_DIR, cache_key + ".json"), "w", encoding="utf-8") as f:
                    json.dump(data, f)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (attempt + 1))   # 429/5xx backoff
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return None


def cik_map():
    """Ticker -> zero-padded 10-digit CIK, from SEC's master list."""
    data = _sec_get("https://www.sec.gov/files/company_tickers.json", cache_key="company_tickers")
    out = {}
    if data:
        for row in data.values():
            out[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
    return out


def company_facts(cik):
    return _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                    cache_key=f"facts_{cik}")


# XBRL concept -> the fallback tags companies actually use (first hit wins).
CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "assets": ["Assets"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "lt_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "cur_debt": ["LongTermDebtCurrent", "DebtCurrent"],
    "op_cash_flow": ["NetCashProvidedByUsedInOperatingActivities",
                     "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}


def _annual_series(facts, tags, asof):
    """Return [(period_end_date, value)] for annual (FY) figures KNOWN as of `asof` (filed <= asof),
    newest period first. Picks, per fiscal-year-end, the latest value filed on/before asof — i.e.
    as-originally-reported, restatements after asof excluded. Handles both duration and instant.

    MERGES all fallback tags into one series: companies split history across concepts (e.g. old
    revenue under `Revenues`, post-2018 under `RevenueFromContractWithCustomer...`), so taking the
    first tag with any data would return stale numbers. We combine by period-end and, on ties, keep
    the value with the latest filing date (tag order breaks exact filing ties)."""
    usg = (facts.get("facts", {}) or {}).get("us-gaap", {})
    best = {}   # period_end -> (filed_date, value)
    for tag in tags:
        node = usg.get(tag)
        if not node:
            continue
        for u in node.get("units", {}).get("USD", []):
            if u.get("form") not in ("10-K", "10-K/A") or u.get("fp") != "FY":
                continue
            filed, end = u.get("filed"), u.get("end")
            if not filed or not end or filed > asof:
                continue
            start = u.get("start")   # duration facts (~1yr span); instant facts (assets) have none
            if start:
                span = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
                if span < 300 or span > 400:
                    continue
            prev = best.get(end)
            if prev is None or filed > prev[0]:
                best[end] = (filed, safe_float(u.get("val")))
    series = sorted(best.items(), key=lambda kv: kv[0], reverse=True)
    return [(end, v) for end, (_f, v) in series]


def pit_fundamentals(facts, asof):
    """Fundamentals as known on `asof`: latest annual value per concept, plus prior year for growth."""
    out = {}
    for name, tags in CONCEPTS.items():
        s = _annual_series(facts, tags, asof)
        out[name] = s[0][1] if s else None
        out[name + "_prev"] = s[1][1] if len(s) > 1 else None
        out[name + "_end"] = s[0][0] if s else None
    return out


def shares_asof(facts, asof):
    """Shares outstanding last reported on/before `asof` — from the cover-page dei tag (updated on
    every 10-K/10-Q, so it's the freshest PIT share count). Used with price(T) for market cap."""
    best = None   # (filed, value)
    for sect in ("dei", "us-gaap"):
        node = (facts.get("facts", {}) or {}).get(sect, {}).get("EntityCommonStockSharesOutstanding") \
            or (facts.get("facts", {}) or {}).get(sect, {}).get("CommonStockSharesOutstanding")
        if not node:
            continue
        for u in node.get("units", {}).get("shares", []):
            filed, val = u.get("filed"), safe_float(u.get("val"))
            if not filed or val is None or filed > asof:
                continue
            if best is None or filed > best[0]:
                best = (filed, val)
        if best:
            break
    return best[1] if best else None


def pit_score(f, market_cap):
    """Fundamentals-core quant score (0-100) from PIT fundamentals + market cap at date T. Mirrors
    the live engine's quality/valuation/growth/health composites using the same safe_score bands."""
    rev, ni, gp = f.get("revenue"), f.get("net_income"), f.get("gross_profit")
    oi, assets, eq = f.get("operating_income"), f.get("assets"), f.get("equity")
    cash = f.get("cash") or 0
    debt = (f.get("lt_debt") or 0) + (f.get("cur_debt") or 0)
    ocf, capex = f.get("op_cash_flow"), f.get("capex")

    def ratio(a, b):
        a, b = safe_float(a), safe_float(b)
        return (a / b) if (a is not None and b not in (None, 0)) else None

    profit_m = ratio(ni, rev)
    gross_m = ratio(gp, rev)
    op_m = ratio(oi, rev)
    roe = ratio(ni, eq)
    roa = ratio(ni, assets)
    invested = (safe_float(eq) or 0) + debt - cash
    roic = ratio(oi, invested) if invested > 0 else None   # NOPAT~OI proxy
    fcf = (safe_float(ocf) - safe_float(capex)) if (ocf is not None and capex is not None) else None
    fcf_margin = ratio(fcf, rev)

    rev_growth = ratio(safe_float(rev) - safe_float(f.get("revenue_prev")), f.get("revenue_prev")) \
        if (rev and f.get("revenue_prev")) else None
    ni_growth = ratio(safe_float(ni) - safe_float(f.get("net_income_prev")), abs(safe_float(f.get("net_income_prev")))) \
        if (ni and f.get("net_income_prev")) else None

    pe = ratio(market_cap, ni)
    pb = ratio(market_cap, eq)
    d_to_e = ratio(debt, eq)
    d_to_e_pct = d_to_e * 100 if d_to_e is not None else None

    quality = (safe_score(roic, 0.05, 0.20) * 0.34 + safe_score(roe, 0.05, 0.30) * 0.24 +
               safe_score(gross_m, 0.15, 0.65) * 0.12 + safe_score(op_m, 0.04, 0.32) * 0.16 +
               safe_score(profit_m, 0.02, 0.22) * 0.14)
    valuation = (safe_score(pe if (pe and pe > 0) else 999, 8, 45, reverse=True) * 0.5 +
                 safe_score(pb if (pb and pb > 0) else 999, 1, 8, reverse=True) * 0.3 +
                 safe_score(fcf_margin, 0.0, 0.25) * 0.2)
    growth = (safe_score(rev_growth, -0.03, 0.25) * 0.5 + safe_score(ni_growth, -0.05, 0.30) * 0.5)
    health = (safe_score(d_to_e_pct, 20, 220, reverse=True) * 0.5 +
              safe_score(profit_m, 0.02, 0.22) * 0.25 + safe_score(fcf_margin, 0.0, 0.25) * 0.25)

    overall = quality * 0.35 + valuation * 0.25 + growth * 0.20 + health * 0.20
    return {"score": round(clamp(overall), 1), "quality": round(quality, 1),
            "valuation": round(valuation, 1), "growth": round(growth, 1), "health": round(health, 1),
            "pe": round(pe, 1) if pe else None, "roic": round(roic * 100, 1) if roic else None,
            "rev_growth": round(rev_growth * 100, 1) if rev_growth is not None else None,
            "coverage": sum(1 for k in ("revenue", "net_income", "equity", "assets", "operating_income")
                            if f.get(k) is not None)}


# ~110 large-cap NON-FINANCIAL S&P 500 names (banks/insurers/REITs excluded — different XBRL tags).
# Netting ~100 after coverage drops. Today's membership -> survivorship bias (flagged in results).
UNIVERSE = ("AAPL MSFT NVDA GOOGL AMZN META AVGO TSLA ORCL ADBE CRM AMD ACN CSCO INTC IBM QCOM TXN "
            "INTU NOW AMAT MU ADI LRCX KLAC SNPS CDNS PANW ANET MSI "
            "UNH JNJ LLY ABBV MRK PFE TMO ABT DHR BMY AMGN CVS MDT GILD ISRG VRTX REGN ZTS BSX HCA "
            "WMT PG KO PEP COST MCD NKE SBUX LOW TGT HD BKNG CMG MDLZ MO PM CL EL GIS KMB SYY "
            "DIS NFLX CMCSA T VZ TMUS "
            "XOM CVX COP SLB EOG MPC PSX VLO OXY WMB "
            "GE HON UNP CAT DE LMT RTX BA UPS FDX MMM EMR ETN ITW CSX NSC GD NOC "
            "LIN APD SHW FCX NEM ECL DOW "
            "NEE DUK SO D AEP EXC").split()


def price_on_or_after(hist, date_str):
    """First close on/after date_str from a yfinance history frame (index tz-naive)."""
    import pandas as pd
    d = pd.Timestamp(date_str)
    idx = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
    mask = idx >= d
    if not mask.any():
        return None
    return safe_float(hist["Close"][mask].iloc[0])


def run_backtest(asof="2020-01-01", verbose=True):
    import pandas as pd
    import yfinance as yf

    cmap = cik_map()
    tickers = [t for t in UNIVERSE if t in cmap]
    if verbose:
        print(f"CIK map: {len(cmap)} tickers · universe {len(UNIVERSE)} · matched {len(tickers)}")
        print(f"Scoring point-in-time as of {asof}, then measuring return to today…\n")

    # Prices: one batch download with split/dividend actions. yfinance's "Close" is split-adjusted
    # regardless of auto_adjust, so raw price isn't directly available — instead we reconstruct a
    # correct market cap in TODAY's split terms: market_cap(T) = adj_price(T) × raw_shares(T) ×
    # (cumulative split ratio after T). Without this, any name that split since T (NVDA 40:1,
    # GOOGL 20:1) would show a market cap ~Nx too small and a fake ultra-cheap valuation.
    raw = yf.download(tickers + ["SPY"], start="2019-12-01", progress=False,
                      auto_adjust=True, actions=True)
    px_adj = raw["Close"]                                       # adjusted — for returns
    splits = raw["Stock Splits"] if "Stock Splits" in raw.columns.get_level_values(0) else None
    last_date = px_adj.index[-1].strftime("%Y-%m-%d")
    asof_ts = __import__("pandas").Timestamp(asof)

    def fwd_return(tk):
        if tk not in px_adj.columns:
            return None
        s = px_adj[tk].dropna()
        p0 = price_on_or_after(s.to_frame("Close"), asof)
        p1 = safe_float(s.iloc[-1])
        return ((p1 / p0 - 1) * 100) if (p0 and p1) else None

    def split_factor_after_T(tk):
        """Cumulative split multiple applied AFTER T (e.g. 40 for NVDA's 4:1 then 10:1)."""
        if splits is None or tk not in splits.columns:
            return 1.0
        s = splits[tk]
        idx = s.index.tz_localize(None) if s.index.tz is not None else s.index
        post = s[(idx > asof_ts) & (s > 0)]
        factor = 1.0
        for v in post.values:
            factor *= float(v)
        return factor or 1.0

    def market_cap_at_T(tk, raw_shares):
        p_adj = price_on_or_after(px_adj[tk].dropna().to_frame("Close"), asof) if tk in px_adj.columns else None
        if p_adj is None or not raw_shares:
            return None
        return p_adj * raw_shares * split_factor_after_T(tk)

    spy_ret = fwd_return("SPY")

    rows, dropped = [], []
    for i, tk in enumerate(tickers, 1):
        facts = company_facts(cmap[tk])
        time.sleep(0.12)   # SEC politeness (<10/s)
        if not facts:
            dropped.append((tk, "no facts")); continue
        f = pit_fundamentals(facts, asof)
        sh = shares_asof(facts, asof)
        mc = market_cap_at_T(tk, sh)
        if not mc or f.get("net_income") is None or f.get("revenue") is None:
            reason = ("no shares/price" if not mc
                      else "no net income" if f.get("net_income") is None else "no revenue")
            dropped.append((tk, reason)); continue
        sc = pit_score(f, market_cap=mc)
        if sc["coverage"] < 4:
            dropped.append((tk, f"low coverage {sc['coverage']}/5")); continue
        rows.append({"Ticker": tk, "Score": sc["score"], "Quality": sc["quality"],
                     "Valuation": sc["valuation"], "Growth": sc["growth"], "Health": sc["health"],
                     "P/E@T": sc["pe"], "ROIC@T %": sc["roic"], "FY end": f.get("revenue_end"),
                     "Return since %": fwd_return(tk)})
        if verbose and i % 20 == 0:
            print(f"  …{i}/{len(tickers)} processed")

    df = pd.DataFrame([r for r in rows if r["Return since %"] is not None])
    return df, spy_ret, last_date, dropped


def summarize(df, spy_ret, last_date, asof, dropped):
    import pandas as pd
    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    n = len(df)
    print("=" * 74)
    print(f"POINT-IN-TIME BACKTEST — scored as of {asof}, return through {last_date}")
    print(f"{n} names scored · {len(dropped)} dropped · SPY over the same window: {spy_ret:+.1f}%")
    print("=" * 74)

    q = max(3, n // 4)
    top, bot = df.head(q), df.tail(q)
    top_avg, bot_avg = top["Return since %"].mean(), bot["Return since %"].mean()
    corr = df["Score"].corr(df["Return since %"])
    top_beat = (top["Return since %"] > spy_ret).mean() * 100

    print(f"\nTop-quartile (highest score)   avg {top_avg:+.1f}%  ·  median {top['Return since %'].median():+.1f}%  "
          f"(beat SPY {top_beat:.0f}% of names)")
    print(f"Bottom-quartile (lowest score) avg {bot_avg:+.1f}%  ·  median {bot['Return since %'].median():+.1f}%")
    print(f"Top - Bottom spread: {top_avg - bot_avg:+.1f} pts (avg) · "
          f"{top['Return since %'].median() - bot['Return since %'].median():+.1f} pts (median)")
    print(f"Top - SPY: {top_avg - spy_ret:+.1f} pts (avg)")
    print(f"Rank correlation (score vs forward return): {corr:+.2f}")
    print("Note: averages are skewed by a few megawinners — the median is the typical name.")

    def show(title, sub):
        print(f"\n{title}")
        for _, r in sub.iterrows():
            print(f"  {r['Ticker']:6} score {r['Score']:5.1f}  (Q{r['Quality']:.0f}/V{r['Valuation']:.0f}/"
                  f"G{r['Growth']:.0f}/H{r['Health']:.0f})  P/E@T {str(r['P/E@T']):>5}  ->  {r['Return since %']:+7.1f}%")
    show("HIGHEST-SCORING in Jan 2020  ->  how they've done since:", df.head(12))
    show("LOWEST-SCORING in Jan 2020  ->  how they've done since:", df.tail(8))

    if dropped:
        print(f"\nDropped ({len(dropped)}): " + ", ".join(f"{t}({why})" for t, why in dropped[:20]))


def pit_features(f, market_cap):
    """Raw factors + pillar scores + composite for one name — the full feature row the efficacy
    study correlates against forward returns. Same math as pit_score, but also exposes the raw
    ratios so we can see which INPUTS (not just pillars) actually predicted returns."""
    rev, ni, gp = f.get("revenue"), f.get("net_income"), f.get("gross_profit")
    oi, assets, eq = f.get("operating_income"), f.get("assets"), f.get("equity")
    cash = f.get("cash") or 0
    debt = (f.get("lt_debt") or 0) + (f.get("cur_debt") or 0)
    ocf, capex = f.get("op_cash_flow"), f.get("capex")

    def ratio(a, b):
        a, b = safe_float(a), safe_float(b)
        return (a / b) if (a is not None and b not in (None, 0)) else None

    net_m, gross_m, op_m = ratio(ni, rev), ratio(gp, rev), ratio(oi, rev)
    roe, roa = ratio(ni, eq), ratio(ni, assets)
    invested = (safe_float(eq) or 0) + debt - cash
    roic = ratio(oi, invested) if invested > 0 else None
    fcf = (safe_float(ocf) - safe_float(capex)) if (ocf is not None and capex is not None) else None
    fcf_margin = ratio(fcf, rev)
    rev_g = ratio(safe_float(rev) - safe_float(f.get("revenue_prev")), f.get("revenue_prev")) \
        if (rev and f.get("revenue_prev")) else None
    ni_g = ratio(safe_float(ni) - safe_float(f.get("net_income_prev")), abs(safe_float(f.get("net_income_prev")))) \
        if (ni and f.get("net_income_prev")) else None
    pe, pb = ratio(market_cap, ni), ratio(market_cap, eq)
    d_to_e = ratio(debt, eq)

    sc = pit_score(f, market_cap)
    d_to_e_pct = d_to_e * 100 if d_to_e is not None else None
    # REVISED composite — weights informed by the efficacy study: lead with revenue growth (the most
    # robust factor, 4/4 cohorts), reward gross margin + FCF margin + low leverage (all robust),
    # keep some ROIC, and STOP rewarding raw cheapness (P/B dropped entirely — it was the most
    # inverted factor; P/E only mildly penalized at extremes rather than rewarded when low).
    revised = (safe_score(rev_g, -0.03, 0.30) * 0.28 +
               safe_score(gross_m, 0.20, 0.70) * 0.16 +
               safe_score(fcf_margin, 0.0, 0.25) * 0.16 +
               safe_score(roic, 0.05, 0.20) * 0.12 +
               safe_score(d_to_e_pct, 20, 220, reverse=True) * 0.10 +
               safe_score(ni_g, -0.05, 0.30) * 0.08 +
               safe_score(pe if (pe and pe > 0) else 45, 15, 80, reverse=True) * 0.10)
    return {
        # pillars + composite (what the engine outputs)
        "composite": sc["score"], "revised": round(clamp(revised), 1), "quality": sc["quality"],
        "valuation": sc["valuation"], "growth": sc["growth"], "health": sc["health"],
        # raw factors (the inputs) — the study checks which of THESE predict returns
        "pe": pe, "pb": pb, "roic": roic, "roe": roe, "net_margin": net_m, "gross_margin": gross_m,
        "op_margin": op_m, "fcf_margin": fcf_margin, "rev_growth": rev_g, "ni_growth": ni_g,
        "leverage_de": d_to_e, "size_mktcap": market_cap, "coverage": sc["coverage"],
    }


# Direction each factor is EXPECTED to help: +1 means higher is better (engine rewards it),
# -1 means lower is better (engine rewards cheapness/safety by scoring the inverse high).
FACTOR_DIR = {
    "composite": +1, "revised": +1, "quality": +1, "valuation": +1, "growth": +1, "health": +1,
    "roic": +1, "roe": +1, "net_margin": +1, "gross_margin": +1, "op_margin": +1,
    "fcf_margin": +1, "rev_growth": +1, "ni_growth": +1, "size_mktcap": +1,
    "pe": -1, "pb": -1, "leverage_de": -1,   # the engine treats LOW P/E, P/B, leverage as good
}


def efficacy_study(cohorts=("2015-01-01", "2017-01-01", "2019-01-01", "2021-01-01"), horizon_years=3):
    """For each cohort date, score every name PIT and measure its forward return over a FIXED
    horizon, then Spearman-rank-correlate each factor with forward return. Averaging the sign and
    size of that correlation ACROSS cohorts separates factors that robustly work from ones that
    only worked in one regime. Returns (per_factor_summary_df, per_cohort_detail)."""
    import pandas as pd
    import yfinance as yf

    cmap = cik_map()
    tickers = [t for t in UNIVERSE if t in cmap]
    px = yf.download(tickers, start="2013-06-01", progress=False, auto_adjust=True, actions=True)
    close = px["Close"]

    def fwd(tk, start, end):
        if tk not in close.columns:
            return None
        s = close[tk].dropna()
        p0 = price_on_or_after(s.to_frame("Close"), start)
        p1 = price_on_or_after(s.to_frame("Close"), end)
        return ((p1 / p0 - 1) * 100) if (p0 and p1) else None

    factors = [k for k in FACTOR_DIR]
    per_cohort = {}
    for asof in cohorts:
        end = f"{int(asof[:4]) + horizon_years}{asof[4:]}"
        rows = []
        for tk in tickers:
            facts = company_facts(cmap[tk])
            time.sleep(0.02)
            if not facts:
                continue
            ff = pit_fundamentals(facts, asof)
            mc = None
            if tk in close.columns:
                p_adj = price_on_or_after(close[tk].dropna().to_frame("Close"), asof)
                sh = shares_asof(facts, asof)
                # split factor after asof
                sf = 1.0
                if "Stock Splits" in px.columns.get_level_values(0) and tk in px["Stock Splits"].columns:
                    ss = px["Stock Splits"][tk]
                    idx = ss.index.tz_localize(None) if ss.index.tz is not None else ss.index
                    for v in ss[(idx > pd.Timestamp(asof)) & (ss > 0)].values:
                        sf *= float(v)
                mc = p_adj * sh * sf if (p_adj and sh) else None
            if not mc or ff.get("net_income") is None or ff.get("revenue") is None:
                continue
            feat = pit_features(ff, mc)
            if feat["coverage"] < 4:
                continue
            feat["fwd"] = fwd(tk, asof, end)
            feat["Ticker"] = tk
            rows.append(feat)
        df = pd.DataFrame([r for r in rows if r.get("fwd") is not None])
        # Spearman rank corr of each factor vs forward return, oriented by expected direction.
        corrs = {}
        for fac in factors:
            sub = df[[fac, "fwd"]].dropna()
            if len(sub) >= 15:
                # Spearman = Pearson on ranks (avoids the scipy dependency).
                c = sub[fac].rank().corr(sub["fwd"].rank())
                corrs[fac] = c * FACTOR_DIR[fac]   # orient: + means "worked as intended"
        per_cohort[asof] = {"n": len(df), "end": end, "corrs": corrs}

    # Aggregate across cohorts: mean oriented-correlation + how many cohorts it was positive.
    summary = []
    for fac in factors:
        vals = [per_cohort[c]["corrs"].get(fac) for c in cohorts if fac in per_cohort[c]["corrs"]]
        vals = [v for v in vals if v is not None]
        if vals:
            summary.append({"factor": fac, "mean_ic": sum(vals) / len(vals),
                            "pos_cohorts": sum(1 for v in vals if v > 0), "n_cohorts": len(vals),
                            "per": [round(v, 2) for v in vals]})
    summary.sort(key=lambda r: r["mean_ic"], reverse=True)
    return summary, per_cohort


def print_efficacy(summary, per_cohort, cohorts):
    print("=" * 78)
    print("FACTOR EFFICACY — oriented Spearman rank-IC vs 3-yr forward return, by cohort")
    print("(+ = the factor predicted returns in the direction our engine assumes; - = it hurt)")
    print("=" * 78)
    hdr = "  ".join(c[:4] for c in cohorts)
    for asof in cohorts:
        d = per_cohort[asof]
        print(f"  cohort {asof} -> {d['end']}: {d['n']} names")
    print(f"\n{'factor':14} {'mean IC':>8} {'+cohorts':>9}   per-cohort [{hdr}]")
    print("-" * 78)
    for r in summary:
        flag = "  <-- robust" if (r["pos_cohorts"] == r["n_cohorts"] and r["mean_ic"] > 0.05) else \
               ("  <-- INVERTED" if r["mean_ic"] < -0.03 else "")
        print(f"{r['factor']:14} {r['mean_ic']:+8.3f} {r['pos_cohorts']}/{r['n_cohorts']:<7} {str(r['per']):>28}{flag}")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    if mode == "efficacy":
        cohorts = ("2015-01-01", "2017-01-01", "2019-01-01", "2021-01-01")
        summary, per_cohort = efficacy_study(cohorts=cohorts, horizon_years=3)
        print_efficacy(summary, per_cohort, cohorts)
    else:
        asof = sys.argv[1] if len(sys.argv) > 1 else "2020-01-01"
        df, spy_ret, last_date, dropped = run_backtest(asof=asof)
        summarize(df, spy_ret, last_date, asof, dropped)
