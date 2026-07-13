# 📈 Mastermind Quant Terminal

**A full-stack equity research terminal that scores the entire S&P 500 on institutional-grade fundamentals, values companies with a discounted-cash-flow model, and — crucially — honestly measures whether its own signals actually predict returns.**

🔗 **Live app:** https://quant-terminal-museq45xbpxspebjedgotf.streamlit.app/
💻 **Built with:** Python · Streamlit · pandas · Plotly · Financial Modeling Prep (SEC data) · Yahoo Finance · GitHub Actions

> ⚠️ **Not financial advice.** This is a research tool that surfaces ideas to study further. It does not tell anyone what to buy or sell.

---

## Why I built it

I wanted to learn how professional equity research actually works — factor investing, valuation, and the discipline of testing whether a strategy has any real edge — by building the thing end to end rather than reading about it. The guiding principle throughout was **intellectual honesty**: it would have been easy to make a backtest that looks impressive; the hard (and useful) part is building tools that tell you the truth, including when the model *doesn't* work.

---

## What it does

A 14-page terminal covering the full research workflow:

### Research & discovery
- **Quant Opportunity Engine** — scans the **full S&P 500** and scores every name across 8 factors (quality, valuation, growth, cash flow, financial strength, momentum, relative strength, risk), rolled into composite Investment / Opportunity / Conviction scores. Includes an **Opportunity Map** (valuation-vs-quality scatter) and **sector-relative** rankings (a bank vs. banks, not vs. software).
- **Research Queue** — a prioritized daily list, bucketed by conviction / value / recovery / momentum.
- **Stock Deep Dive** — per-stock breakdown: factor radar, price + fair-value band, trailing *and* forward analyst view, and an optional AI-written research memo.
- **ETF Explorer** — cost / yield / returns / risk, sector weightings, and top holdings for any fund.

### Valuation (the honest part)
- A **fair-value range**, not a false-precision single number — blended from P/E, EV/FCF, a **2-stage DCF**, PEG, and 52-week methods, each capped and combined by median so no single method distorts it. A traffic-light flag warns when the methods disagree.
- **Valuation Lab** — an interactive DCF where you move growth / discount / terminal-rate sliders and watch fair value respond, with a sensitivity table.
- **Forward-looking factors** — analyst estimate-revisions momentum, earnings-surprise track record, and a forward-EPS valuation.

### Portfolio & personalization
- **Portfolio Manager** — holdings analysis, hold/add/trim/sell guidance, a new-money allocator, and **risk analytics** (portfolio beta, concentration / effective positions, and a holdings-correlation heatmap — "am I actually diversified?").
- **Watchlist** with live alerts and an upcoming-earnings calendar (persists via URL so it survives across devices).
- **Strategy Builder** — set your own factor weights (or pick a Value / GARP / Quality / Momentum preset) and re-rank the whole market by *your* style.

### Proving it works (or doesn't)
- **Backtesting Lab** — a methodologically **honest point-in-time backtest** (ranks by the scores you had on a past date, measures the returns that followed — no lookahead bias), alongside a clearly-labeled illustrative one.
- **Factor Efficacy** — using accumulated scan history, measures each factor's **Information Coefficient** (rank correlation of score vs. realized forward return) and top-vs-bottom return spread. This is the honest answer to "does the engine actually work?" — and it's refreshingly willing to say "not yet / not this factor."

---

## 📸 Screenshots

Best experienced live: **https://quant-terminal-museq45xbpxspebjedgotf.streamlit.app/**

Worth a look: the **Opportunity Map** (valuation-vs-quality scatter), a **Deep Dive** (factor radar + fair-value band + analyst view), the interactive **Valuation Lab**, and the **Factor Efficacy** table.

<!-- To embed images: create a docs/ folder, drop in PNGs, and uncomment:
| | |
|---|---|
| ![Opportunity Map](docs/opportunity-map.png) | ![Deep Dive](docs/deep-dive.png) |
| ![Valuation Lab](docs/valuation-lab.png) | ![Factor Efficacy](docs/factor-efficacy.png) |
-->


---

## 🧠 Methodology highlights

- **Data integrity first.** Fundamentals come from Financial Modeling Prep (sourced from SEC filings). When data is missing or a ticker is delisted, it is **skipped — never given a fake neutral score** — and every result carries a data-coverage %. An automated weekly audit re-checks the app's numbers against source-of-truth.
- **Like-for-like comparison.** Sector-relative percentiles avoid the classic mistake of comparing a bank's valuation to a software company's.
- **Honest valuation.** Fair value is a *range* from multiple methods (incl. DCF), median-blended and outlier-capped — not one number pretending to be precise.
- **No lookahead bias.** The backtest ranks on point-in-time scores and measures forward returns; the factor-efficacy tool then quantifies whether any of it has predictive power.

---

## 🏗️ Architecture & automation

- **`dashboard.py`** — the Streamlit app (all pages, scoring engine, valuation, charts).
- **`run_scan.py` + GitHub Actions** — a scheduled job scans a rotating slice of the S&P 500 **every weekday**, so the whole index refreshes ~every two weeks within API limits, and commits results back to the repo (which auto-redeploys the live app). A separate weekend job runs the accuracy audit. *The app maintains and re-verifies itself, unattended.*
- **Pluggable data layer** — uses FMP when a key is present, gracefully falls back to Yahoo Finance otherwise, so it always runs.

---

## ▶️ Run it locally

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
.venv/Scripts/streamlit.exe run dashboard.py
```
Then open http://localhost:8501.

**Optional API keys** (copy `.env.example` → `.env`):
- `FMP_API_KEY` — Financial Modeling Prep, for SEC-sourced fundamentals (free tier works; the app falls back to Yahoo without it).
- `OPENAI_API_KEY` — enables the AI research-memo tab (fully optional).

---

## ⚠️ Disclaimer

This is an educational research tool, not investment advice. It relies on free/best-effort data that can be delayed or wrong, and — as its own Factor Efficacy tab will tell you — no scoring model reliably predicts future returns. Do your own research.
