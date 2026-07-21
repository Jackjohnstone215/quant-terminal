"""Precompute the market forecast into forecast_cache.json so the app serves it instantly.

Runs in the daily GitHub Action (alongside run_scan). The forecast needs ~25 slow web/FRED/Yahoo
calls plus several regressions and backtests; doing that on every Streamlit Cloud cold-start is
what made the app feel slow. This computes the whole bundle once a day and commits it; the app
reads the committed file (instant) and only falls back to a live compute if it's missing/stale.

Never fails the job: if sources are unreachable it just leaves the existing cache in place.
"""
import json
import datetime
import dashboard as d


def main():
    try:
        bundle = d._compute_forecast_bundle()
    except Exception as e:
        print(f"Forecast compute error (non-fatal): {str(e)[:160]}", flush=True)
        return
    if not bundle or not bundle.get("val"):
        print("Forecast bundle empty (sources unreachable) — leaving existing cache untouched.", flush=True)
        return
    bundle["generated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("forecast_cache.json", "w", encoding="utf-8") as f:
        json.dump(bundle, f, default=str)   # default=str serializes backtest Timestamps
    cons = bundle.get("cons") or {}
    print(f"Wrote forecast_cache.json (generated {bundle['generated']}; "
          f"consensus {cons.get('consensus')}%/yr nominal).", flush=True)


if __name__ == "__main__":
    main()
