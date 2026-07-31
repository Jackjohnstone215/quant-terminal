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


_FACTS_MEM = {}   # CIK -> parsed companyfacts, so the multi-MB JSON is parsed once, not per cohort


def company_facts(cik):
    if cik in _FACTS_MEM:
        return _FACTS_MEM[cik]
    path = os.path.join(CACHE_DIR, f"facts_{cik}.json")
    on_disk = os.path.exists(path)
    data = _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                    cache_key=f"facts_{cik}")
    if not on_disk:
        time.sleep(0.1)   # SEC politeness only on an actual network fetch (<10/s)
    _FACTS_MEM[cik] = data
    return data


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
    "div_yield": +1,   # hypothesis under test: does a HIGHER dividend yield predict higher returns?
    "momentum": +1, "rel_strength": +1, "composite_v3": +1,   # price factors + evidence composite
    "pe": -1, "pb": -1, "leverage_de": -1, "low_vol": -1,   # LOW P/E, P/B, leverage, volatility = good
}


def sp500_nonfin():
    """Full current S&P 500 minus Financials/Real Estate (different XBRL tags) — the wide universe.
    Still survivorship-biased to TODAY's membership (flagged), but ~3.5x the hand-picked list."""
    import pandas as pd, urllib.request, io
    try:
        req = urllib.request.Request("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                                     headers={"User-Agent": "Mozilla/5.0 research"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        df = pd.read_html(io.StringIO(html))[0]
        nf = df[~df["GICS Sector"].isin(["Financials", "Real Estate"])]
        return [str(s).replace(".", "-").upper() for s in nf["Symbol"].tolist()]
    except Exception:
        return list(UNIVERSE)


def efficacy_study(cohorts=("2015-01-01", "2017-01-01", "2019-01-01", "2021-01-01"),
                   horizon_years=3, universe=None):
    """For each cohort date, score every name PIT and measure its forward return over a FIXED
    horizon, then Spearman-rank-correlate each factor with forward return. Averaging the sign and
    size of that correlation ACROSS cohorts separates factors that robustly work from ones that
    only worked in one regime. Returns (per_factor_summary_df, per_cohort_detail)."""
    import pandas as pd
    import yfinance as yf

    cmap = cik_map()
    tickers = [t for t in (universe or UNIVERSE) if t in cmap]
    px = yf.download(tickers + ["SPY"], start="2013-06-01", progress=False, auto_adjust=True, actions=True)
    close = px["Close"]
    divs = px["Dividends"] if "Dividends" in px.columns.get_level_values(0) else None
    spy = close["SPY"].dropna() if "SPY" in close.columns else None

    def _px_at(tk, d):
        return price_on_or_after(close[tk].dropna().to_frame("Close"), d) if tk in close.columns else None

    def momentum_12_1(tk, asof):
        """Classic 12-1 momentum: return from T-12mo to T-1mo (skip the last month to avoid short-
        term reversal). The single strongest factor in the academic literature — untested here until now."""
        a = _px_at(tk, (pd.Timestamp(asof) - pd.Timedelta(days=365)).strftime("%Y-%m-%d"))
        b = _px_at(tk, (pd.Timestamp(asof) - pd.Timedelta(days=30)).strftime("%Y-%m-%d"))
        return (b / a - 1) if (a and b) else None

    def rel_strength_12m(tk, asof):
        """Trailing-12mo return MINUS SPY's — outperformance vs the market."""
        st = (pd.Timestamp(asof) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
        a, b = _px_at(tk, st), _px_at(tk, asof)
        if spy is None or not (a and b):
            return None
        sa = price_on_or_after(spy.to_frame("Close"), st)
        sb = price_on_or_after(spy.to_frame("Close"), asof)
        return (b / a - sb / sa) if (sa and sb) else None

    def vol_12m(tk, asof):
        """Trailing-12mo daily-return volatility (the low-volatility factor; lower has paid off)."""
        if tk not in close.columns:
            return None
        s = close[tk].dropna()
        idx = s.index.tz_localize(None) if s.index.tz is not None else s.index
        win = s[(idx > pd.Timestamp(asof) - pd.Timedelta(days=365)) & (idx <= pd.Timestamp(asof))]
        return float(win.pct_change().dropna().std()) if len(win) >= 60 else None

    def ttm_div_yield(tk, asof):
        """Trailing-12-month dividends per share / price at T — point-in-time, no lookahead. A
        non-payer returns 0.0 (so it's ranked as low-yield, not dropped). Div and price are both
        split-adjusted, so the ratio is correct."""
        p0 = price_on_or_after(close[tk].dropna().to_frame("Close"), asof) if tk in close.columns else None
        if not p0:
            return None
        if divs is None or tk not in divs.columns:
            return 0.0
        s = divs[tk]
        idx = s.index.tz_localize(None) if s.index.tz is not None else s.index
        lo = pd.Timestamp(asof) - pd.Timedelta(days=365)
        ttm = s[(idx > lo) & (idx <= pd.Timestamp(asof)) & (s > 0)].sum()
        return float(ttm) / p0 if ttm > 0 else 0.0

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
            feat["div_yield"] = ttm_div_yield(tk, asof)
            mom, rs, vol = momentum_12_1(tk, asof), rel_strength_12m(tk, asof), vol_12m(tk, asof)
            feat["momentum"] = mom
            feat["rel_strength"] = rs
            feat["low_vol"] = vol
            # Evidence-weighted composite: the winners from this study — revenue growth, FCF/gross
            # margin, low leverage, small size — PLUS the price factors the fundamental engine
            # underweights (momentum, low volatility). This is the "what history says a ranking
            # should look like" candidate, to compare against the old and revised composites.
            feat["composite_v3"] = round(clamp(
                safe_score(feat.get("rev_growth"), -0.03, 0.30) * 0.20 +
                safe_score(feat.get("fcf_margin"), 0.0, 0.25) * 0.12 +
                safe_score(feat.get("gross_margin"), 0.15, 0.65) * 0.08 +
                safe_score(feat.get("leverage_de"), 0.2, 2.2, reverse=True) * 0.10 +
                safe_score(mc, 8e9, 6e11, reverse=True) * 0.08 +
                safe_score(mom, -0.10, 0.60) * 0.28 +
                safe_score(vol, 0.010, 0.045, reverse=True) * 0.14
            ), 1)
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

    # Aggregate across cohorts: mean oriented-IC, its dispersion, a t-stat, and hit rate. With
    # NON-overlapping annual cohorts the per-year ICs are ~independent, so t = mean*sqrt(n)/std is
    # a fair significance gauge (|t|>2 ~ 95%). With overlapping cohorts treat t as indicative only.
    import statistics as _st
    summary = []
    for fac in factors:
        vals = [per_cohort[c]["corrs"].get(fac) for c in cohorts if fac in per_cohort[c]["corrs"]]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2:
            m = sum(vals) / len(vals)
            sd = _st.pstdev(vals) or 1e-9
            t = m * (len(vals) ** 0.5) / sd
            summary.append({"factor": fac, "mean_ic": m, "t": t, "sd": sd,
                            "pos_cohorts": sum(1 for v in vals if v > 0), "n_cohorts": len(vals)})
    summary.sort(key=lambda r: r["mean_ic"], reverse=True)
    return summary, per_cohort


def top_picks_backtest(asof="2016-01-01", n=20, universe=None, rank_by="revised"):
    """Take the S&P 500 as of `asof`, rank point-in-time by a scoring column, take the top n, and
    measure equal-weight total return to today vs SPY. rank_by='revised' = the new evidence-based
    engine's fundamental core; 'composite' = the old engine. No lookahead (only pre-asof filings)."""
    import pandas as pd
    import yfinance as yf
    universe = universe or sp500_nonfin()
    cmap = cik_map()
    tickers = [t for t in universe if t in cmap]
    start = f"{int(asof[:4]) - 2}{asof[4:]}"
    px = yf.download(tickers + ["SPY"], start=start, progress=False, auto_adjust=True, actions=True)
    close = px["Close"]
    last_date = close.index[-1].strftime("%Y-%m-%d")

    def px_at(tk, d):
        return price_on_or_after(close[tk].dropna().to_frame("Close"), d) if tk in close.columns else None

    def split_after(tk, d):
        sf = 1.0
        if "Stock Splits" in px.columns.get_level_values(0) and tk in px["Stock Splits"].columns:
            ss = px["Stock Splits"][tk]
            idx = ss.index.tz_localize(None) if ss.index.tz is not None else ss.index
            for v in ss[(idx > pd.Timestamp(d)) & (ss > 0)].values:
                sf *= float(v)
        return sf

    now_spy0, now_spy1 = px_at("SPY", asof), (safe_float(close["SPY"].dropna().iloc[-1]) if "SPY" in close.columns else None)
    spy_ret = (now_spy1 / now_spy0 - 1) * 100 if (now_spy0 and now_spy1) else None

    rows = []
    for tk in tickers:
        facts = company_facts(cmap[tk])
        if not facts:
            continue
        ff = pit_fundamentals(facts, asof)
        p0 = px_at(tk, asof)
        sh = shares_asof(facts, asof)
        if not p0 or not sh or ff.get("net_income") is None or ff.get("revenue") is None:
            continue
        mc = p0 * sh * split_after(tk, asof)
        feat = pit_features(ff, mc)
        if feat["coverage"] < 4:
            continue
        p1 = safe_float(close[tk].dropna().iloc[-1]) if tk in close.columns else None
        feat["Ticker"] = tk
        feat["ret"] = (p1 / p0 - 1) * 100 if (p0 and p1) else None
        rows.append(feat)

    df = pd.DataFrame([r for r in rows if r.get("ret") is not None])
    return df, spy_ret, last_date


def _summarize_picks(df, spy_ret, last_date, asof, n, rank_by, label):
    import statistics as st
    top = df.sort_values(rank_by, ascending=False).head(n)
    rets = top["ret"].tolist()
    avg, med = sum(rets) / len(rets), st.median(rets)
    final = sum(10000.0 / n * (1 + r / 100) for r in rets)
    nbeat = sum(1 for r in rets if r > spy_ret)
    print(f"\n{'=' * 70}\n{label}: top {n} by '{rank_by}' as of {asof} -> {last_date}\n{'=' * 70}")
    print(f"{'Ticker':7}{'score':>7}{'return':>11}   $500 ->")
    for _, r in top.iterrows():
        print(f"{r['Ticker']:7}{r[rank_by]:7.1f}{r['ret']:+10.0f}%  ${500 * (1 + r['ret'] / 100):>8,.0f}")
    print(f"{'-' * 40}")
    print(f"Equal-weight avg {avg:+.0f}%  |  median {med:+.0f}%  |  {nbeat}/{n} beat SPY")
    print(f"$10,000 -> ${final:,.0f}   (SPY +{spy_ret:.0f}% -> ${10000 * (1 + spy_ret / 100):,.0f})")
    return {"avg": avg, "med": med, "final": final, "nbeat": nbeat}


def _growth_wt(rate):
    """Growth weight in [0.6, 1.0] from the 10-yr yield — mirrors the live growth_regime_weight()."""
    if rate is None:
        return 0.85
    return max(0.6, min(1.0, 1.0 - (rate - 2.0) / 3.0 * 0.4))


def revised_regime_score(feat, grw):
    """The 'revised' composite with the RATE-AWARE GROWTH DAMPENER applied: growth's weight scales
    with grw and the freed weight is split to low-leverage and value (soft P/E). Self-normalizing."""
    rg = safe_score(feat.get("rev_growth"), -0.03, 0.30)
    gm = safe_score(feat.get("gross_margin"), 0.15, 0.65)
    fm = safe_score(feat.get("fcf_margin"), 0.0, 0.25)
    rc = safe_score(feat.get("roic"), 0.05, 0.20)
    ll = safe_score(feat.get("leverage_de"), 0.2, 2.2, reverse=True)
    ng = safe_score(feat.get("ni_growth"), -0.05, 0.30)
    pe = feat.get("pe")
    sp = safe_score(pe if (pe and pe > 0) else 45, 15, 80, reverse=True)
    freed = 0.28 * (1 - grw)
    return round(clamp(rg * (0.28 * grw) + gm * 0.16 + fm * 0.16 + rc * 0.12 +
                       ll * (0.10 + freed * 0.5) + ng * 0.08 + sp * (0.10 + freed * 0.5)), 1)


def rolling_backtest(years=range(2016, 2025), n=20, universe=None):
    """For each start year, rank the S&P point-in-time by BOTH engines, hold the top n to today, and
    compare to SPY. One price download, facts cached in memory. Also reports the revised score's IC
    that year (prediction quality) and how much of the top-n's edge is the single best name (tail
    dependence). Returns a list of per-year dicts."""
    import pandas as pd
    import yfinance as yf
    import statistics as st
    universe = universe or sp500_nonfin()
    cmap = cik_map()
    tickers = [t for t in universe if t in cmap]
    px = yf.download(tickers + ["SPY"], start="2009-06-01", progress=False, auto_adjust=True, actions=True)
    close = px["Close"]
    last_date = close.index[-1].strftime("%Y-%m-%d")
    p_now = {tk: safe_float(close[tk].dropna().iloc[-1]) for tk in close.columns if tk in close.columns}

    # 10-yr Treasury history for the point-in-time growth dampener.
    try:
        tnx = yf.Ticker("^TNX").history(start="2009-06-01")["Close"]
        tnx.index = tnx.index.tz_localize(None) if tnx.index.tz is not None else tnx.index
    except Exception:
        tnx = None

    def rate_at(d):
        if tnx is None or not len(tnx):
            return None
        s = tnx[tnx.index <= pd.Timestamp(d)]
        if not len(s):
            return None
        v = float(s.iloc[-1])
        return v / 10 if v > 20 else v

    def px_at(tk, d):
        return price_on_or_after(close[tk].dropna().to_frame("Close"), d) if tk in close.columns else None

    def split_after(tk, d):
        sf = 1.0
        if "Stock Splits" in px.columns.get_level_values(0) and tk in px["Stock Splits"].columns:
            ss = px["Stock Splits"][tk]
            idx = ss.index.tz_localize(None) if ss.index.tz is not None else ss.index
            for v in ss[(idx > pd.Timestamp(d)) & (ss > 0)].values:
                sf *= float(v)
        return sf

    out = []
    for y in years:
        asof = f"{y}-01-01"
        spy0 = px_at("SPY", asof)
        spy_ret = (p_now.get("SPY") / spy0 - 1) * 100 if (spy0 and p_now.get("SPY")) else None
        grw = _growth_wt(rate_at(asof))
        rows = []
        for tk in tickers:
            facts = company_facts(cmap[tk])
            if not facts:
                continue
            ff = pit_fundamentals(facts, asof)
            p0, sh = px_at(tk, asof), shares_asof(facts, asof)
            if not p0 or not sh or ff.get("net_income") is None or ff.get("revenue") is None:
                continue
            feat = pit_features(ff, p0 * sh * split_after(tk, asof))
            if feat["coverage"] < 4 or not p_now.get(tk):
                continue
            feat["regime"] = revised_regime_score(feat, grw)   # growth dampener applied PIT
            feat["Ticker"], feat["ret"] = tk, (p_now[tk] / p0 - 1) * 100
            rows.append(feat)
        df = pd.DataFrame(rows)
        if df.empty or spy_ret is None:
            continue
        # Blend the new (growth-tilted) and old (value-tilted) engines by within-cohort percentile
        # rank, so the two different score scales combine cleanly. Test a couple of mixes.
        rn, ro = df["revised"].rank(pct=True), df["composite"].rank(pct=True)
        df["blend50"] = 0.50 * rn + 0.50 * ro
        df["blend65"] = 0.65 * rn + 0.35 * ro
        ic = rn.corr(df["ret"].rank())
        rec = {"year": y, "horizon": round((pd.Timestamp(last_date) - pd.Timestamp(asof)).days / 365.0, 1),
               "n": len(df), "spy": spy_ret, "ic_revised": ic, "rate": rate_at(asof)}
        for eng, col in (("new", "revised"), ("bl65", "blend65"), ("bl50", "blend50"), ("old", "composite")):
            top = df.sort_values(col, ascending=False).head(n)
            rets = top["ret"].tolist()
            rec[eng] = {"avg": sum(rets) / len(rets), "med": st.median(rets),
                        "beat": sum(1 for r in rets if r > spy_ret)}
        out.append(rec)
    return out, last_date


def print_rolling(out, last_date):
    import statistics as st
    engines = [("NEW", "new"), ("BL65", "bl65"), ("BL50", "bl50"), ("OLD", "old")]
    print(f"\n{'=' * 78}")
    print(f"BLEND TEST: top 20 held to {last_date}. NEW (growth) vs BLEND vs OLD (value) vs SPY.")
    print(f"BL65 = 65% new / 35% old by rank; BL50 = 50/50.")
    print(f"{'=' * 78}")
    print(f"{'start':>5} {'yrs':>4} {'SPY%':>6} | " + " ".join(f"{nm:>6}" for nm, _ in engines) + " | best")
    print("-" * 78)
    for r in out:
        vals = [(nm, r[k]["avg"]) for nm, k in engines]
        best = max(vals, key=lambda x: x[1])[0]
        print(f"{r['year']:>5} {r['horizon']:>4} {r['spy']:>+6.0f} | "
              + " ".join(f"{v:>+6.0f}" for _, v in vals) + f" | {best}")
    print("-" * 78)
    n = len(out)
    print(f"\n{'engine':>6} {'beatSPY':>8} {'mean excess':>12} {'FLOOR (worst)':>14} {'consistency(sd)':>16}")
    print("-" * 78)
    for nm, k in engines:
        ex = [r[k]["avg"] - r["spy"] for r in out]          # excess over SPY per cohort
        beat = sum(1 for e in ex if e > 0)
        print(f"{nm:>6} {beat:>6}/{n} {sum(ex)/len(ex):>+11.0f} {min(ex):>+13.0f} {st.pstdev(ex):>15.0f}")
    print("\nFLOOR = the engine's WORST cohort vs SPY (higher = better downside). A good blend should")
    print("lift the floor (old's strength) without gutting the mean (new's strength).")


def print_efficacy(summary, per_cohort, cohorts, horizon_years=3):
    n_names = int(sum(per_cohort[c]["n"] for c in cohorts) / max(len(cohorts), 1))
    print("=" * 74)
    print(f"FACTOR EFFICACY — oriented rank-IC vs {horizon_years}-yr forward return")
    print(f"{len(cohorts)} cohorts ({cohorts[0][:4]}-{cohorts[-1][:4]}) · ~{n_names} names/cohort · "
          f"(+ = worked as the engine assumes; - = inverted)")
    print("=" * 74)
    print(f"\n{'factor':14} {'mean IC':>8} {'t-stat':>7} {'hit rate':>9}")
    print("-" * 74)
    for r in summary:
        sig = "***" if abs(r["t"]) >= 3 else "**" if abs(r["t"]) >= 2 else "*" if abs(r["t"]) >= 1.5 else ""
        flag = "  <-- robust" if (r["mean_ic"] > 0.03 and r["t"] >= 2) else \
               ("  <-- INVERTED" if (r["mean_ic"] < -0.02 and r["t"] <= -1.5) else "")
        print(f"{r['factor']:14} {r['mean_ic']:+8.3f} {r['t']:+7.2f}{sig:<3} "
              f"{r['pos_cohorts']:>2}/{r['n_cohorts']:<2}{flag}")
    print("\n* |t|>=1.5  ** |t|>=2 (~95%)  *** |t|>=3.  Annual cohorts on a 1-yr horizon are")
    print("non-overlapping, so these t-stats are fair; 3-yr horizons overlap (indicative only).")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    if mode == "efficacy":
        cohorts = ("2015-01-01", "2017-01-01", "2019-01-01", "2021-01-01")
        summary, per_cohort = efficacy_study(cohorts=cohorts, horizon_years=3)
        print_efficacy(summary, per_cohort, cohorts, 3)
    elif mode == "current":
        asof = sys.argv[2] if len(sys.argv) > 2 else "2026-07-20"
        df, _, last_date = top_picks_backtest(asof=asof, n=20)
        top = df.sort_values("revised", ascending=False).head(20).reset_index(drop=True)
        print(f"CURRENT TOP 20 — new engine (revised fundamental core), fundamentals as of latest filings <= {asof}")
        print(f"{'#':>2} {'Ticker':7}{'score':>6}{'P/E':>7}{'rev growth':>11}{'ROIC':>7}")
        for i, r in top.iterrows():
            pe = f"{r['pe']:.0f}" if r.get('pe') and r['pe'] > 0 else "n/a"
            rg = f"{r['rev_growth']*100:+.0f}%" if r.get('rev_growth') is not None else "n/a"
            rc = f"{r['roic']*100:.0f}%" if r.get('roic') is not None else "n/a"
            print(f"{i+1:>2} {r['Ticker']:7}{r['revised']:>6.1f}{pe:>7}{rg:>11}{rc:>7}")
    elif mode == "rolling":
        y0 = int(sys.argv[2]) if len(sys.argv) > 2 else 2011
        out, last_date = rolling_backtest(years=range(y0, 2025), n=20)
        print_rolling(out, last_date)
    elif mode == "topn":
        asof = sys.argv[2] if len(sys.argv) > 2 else "2016-01-01"
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        df, spy_ret, last_date = top_picks_backtest(asof=asof, n=n)
        print(f"S&P 500 non-financials scored point-in-time as of {asof}; {len(df)} names with data.")
        _summarize_picks(df, spy_ret, last_date, asof, n, "revised", "NEW evidence-based engine")
        _summarize_picks(df, spy_ret, last_date, asof, n, "composite", "OLD engine (for comparison)")
    elif mode == "wide":
        # Widened, more rigorous test: full S&P 500 non-financials, 10 non-overlapping annual
        # cohorts on a 1-yr horizon (valid t-stats), plus a 3-yr horizon pass for robustness.
        uni = sp500_nonfin()
        print(f"Wide universe: {len(uni)} S&P 500 non-financials\n")
        annual = tuple(f"{y}-01-01" for y in range(2014, 2024))
        for hz in (1, 3):
            summary, per_cohort = efficacy_study(cohorts=annual, horizon_years=hz, universe=uni)
            print_efficacy(summary, per_cohort, annual, hz)
            print()
    else:
        asof = sys.argv[1] if len(sys.argv) > 1 else "2020-01-01"
        df, spy_ret, last_date, dropped = run_backtest(asof=asof)
        summarize(df, spy_ret, last_date, asof, dropped)
