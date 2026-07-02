# Mastermind Quant Terminal

A personal, data-driven stock research dashboard built with [Streamlit](https://streamlit.io).
It scores stocks across quality, valuation, growth, cash flow, financial strength, momentum,
relative strength, and risk — then rolls those into composite Conviction / Evidence /
Research-Priority scores to answer one question: **what's worth researching today?**

> ⚠️ **Not financial advice.** This is a research aid. It surfaces ideas to study further;
> it does not tell you what to buy or sell.

## Pages
- **Market Command Center** — market-health regime, macro read, ranked news
- **Research Queue** — today's research list, bucketed by conviction / value / recovery / momentum
- **Portfolio Manager AI** — holdings analysis + hold/add/trim/sell guidance + new-money allocator
- **Quant Opportunity Engine** — scan and score the S&P 500
- **Quant Stock Deep Dive** — full per-stock breakdown, incl. an optional AI research memo
- **Backtesting Lab** — an *honest* point-in-time test plus a clearly-labeled illustrative one
- **Learning Center** — plain-English explanations of every metric

## Run it locally (Windows)
```powershell
# from this folder
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\streamlit.exe run dashboard.py
```
Then open http://localhost:8501

## Optional: AI research summaries
The "🤖 AI Analyst" tab uses OpenAI. It's fully optional — the app works without it.
1. Copy `.env.example` to `.env`
2. Add your key: `OPENAI_API_KEY=sk-...` (and optionally `OPENAI_MODEL=gpt-4o-mini`)
3. Restart the app

## Data
Market data comes from Yahoo Finance via `yfinance` (free, best-effort). When Yahoo can't
return reliable data for a ticker, that ticker is **skipped** rather than given a fake score,
and a data-coverage % flags low-confidence results.
