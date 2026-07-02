"""Headless quant scan for scheduled runs (e.g. GitHub Actions).

Imports the scoring engine from dashboard.py but never starts the Streamlit UI, so it can
run on a server/cron. It scores the core watchlist, saves the results, and appends a dated
snapshot to the score history — which is exactly what the honest backtest needs to build a
track record over time.
"""
import sys
import pandas as pd
import dashboard as d


def main():
    # Same universe as the app's core lists — kept stable so the history stays comparable.
    universe = list(dict.fromkeys(d.QUALITY_COMPOUNDERS + d.RECOVERY_WATCHLIST))
    print(f"Scanning {len(universe)} tickers...", flush=True)

    rows, failures = [], []
    for i, ticker in enumerate(universe, 1):
        try:
            rows.append(d.get_quant_score(ticker))
            print(f"[{i}/{len(universe)}] {ticker} OK", flush=True)
        except d.DataUnavailable:
            failures.append(ticker)
            print(f"[{i}/{len(universe)}] {ticker} skipped (no reliable data)", flush=True)
        except Exception as e:
            failures.append(ticker)
            print(f"[{i}/{len(universe)}] {ticker} error: {str(e)[:80]}", flush=True)

    if not rows:
        print("No stocks could be scored (likely rate-limited). Not overwriting existing data.", flush=True)
        sys.exit(1)

    df = pd.DataFrame(rows)
    d.save_sp500_scores(df)
    print(f"\nSaved {len(df)} scores. Skipped {len(failures)}: {failures}", flush=True)


if __name__ == "__main__":
    main()
