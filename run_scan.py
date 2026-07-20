"""Headless quant scan for scheduled runs (GitHub Actions).

Imports the scoring engine from dashboard.py but never starts the Streamlit UI, so it can
run on a server/cron. To cover the whole S&P 500 within the FMP free-tier daily quota
(~250 calls/day, ~4 per stock), it scans a rotating CHUNK of the index each day — a
different slice determined by the calendar day — and MERGES results into the cache. Over
~2 weeks the entire index is refreshed on a rolling basis, which is exactly the steady
stream of dated snapshots the honest backtest and factor-efficacy tools need.

Env overrides: SCAN_CHUNK (names per run, default 55).
"""
import sys
import os
import math
import datetime
import pandas as pd
import dashboard as d


def main():
    chunk = int(os.getenv("SCAN_CHUNK", "55"))
    universe = d.get_sp500_tickers()

    if len(universe) < 50:
        batch, label = universe, "fallback watchlist"
    else:
        n_chunks = max(1, math.ceil(len(universe) / chunk))
        idx = datetime.date.today().timetuple().tm_yday % n_chunks   # rotates by calendar day
        batch = universe[idx * chunk:(idx + 1) * chunk]
        label = f"chunk {idx + 1}/{n_chunks} ({len(batch)} of {len(universe)} S&P 500 names)"

    print(f"Scanning {label}...", flush=True)
    rows, failures = [], []
    for i, ticker in enumerate(batch, 1):
        try:
            rows.append(d.get_quant_score(ticker))
            print(f"[{i}/{len(batch)}] {ticker} OK", flush=True)
        except d.DataUnavailable:
            failures.append(ticker)
            print(f"[{i}/{len(batch)}] {ticker} skipped (no reliable data)", flush=True)
        except Exception as e:
            failures.append(ticker)
            print(f"[{i}/{len(batch)}] {ticker} error: {str(e)[:80]}", flush=True)

    if not rows:
        print("No stocks could be scored (likely rate-limited). Not overwriting existing data.", flush=True)
        sys.exit(1)

    d.save_sp500_scores(pd.DataFrame(rows))   # merge=True -> accumulates coverage, keeps other sectors
    print(f"\nSaved {len(rows)} scores. Skipped {len(failures)}: {failures}", flush=True)

    # Optional Telegram alert on the day's best ideas. Never fatal — a notification failure
    # must not fail the scan (the job that actually matters).
    try:
        import notify
        if notify.telegram_enabled():
            msg = notify.build_scan_alert(rows, label=datetime.date.today().isoformat())
            if msg:
                sent = notify.send_telegram(msg)
                print(f"Telegram alert: {'sent' if sent else 'send failed'}", flush=True)
            else:
                print("Telegram: nothing cleared the alert bar today — no message sent.", flush=True)
        else:
            print("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) — skipping alert.", flush=True)
    except Exception as e:
        print(f"Notify step error (non-fatal): {str(e)[:140]}", flush=True)


if __name__ == "__main__":
    main()
