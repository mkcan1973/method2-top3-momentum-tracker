"""
Daily driver for the top-3 momentum tracker. Every run: marks the
currently-held 3 tickers to market and appends today's portfolio value to
equity_history.csv. Once a month (whenever today's calendar month is past
the last recorded rebalance's month - naturally self-retrying if a run
fails on the actual 1st), re-ranks the live S&P 500 universe by trailing
6-month return and rebalances into the new top 3 at today's open, same
convention as the method2 backtest (rebalance_log.csv's seeded history).
"""

import sys
from pathlib import Path

import pandas as pd

import fetch
import rank
import universe
import build_page

OUT_DIR = Path(__file__).parent
EQUITY_CSV = OUT_DIR / "equity_history.csv"
REBALANCE_CSV = OUT_DIR / "rebalance_log.csv"
SPY_CSV = OUT_DIR / "spy_history.csv"


def _load():
    equity = pd.read_csv(EQUITY_CSV, parse_dates=["date"])
    rebal = pd.read_csv(REBALANCE_CSV)
    return equity, rebal


def _last_holding_state(rebal: pd.DataFrame):
    last = rebal.iloc[-1]
    tickers = last["holdings"].split(",")
    prices = [float(p) for p in last["entry_prices"].split(",")]
    return pd.Period(last["period"], freq="M"), dict(zip(tickers, prices)), float(last["basis_value_per_slot"])


def _mark_to_market(price_dfs: dict, entry_prices: dict, basis_value_per_slot: float, field: str, asof: pd.Timestamp) -> float:
    total = 0.0
    for t, entry_px in entry_prices.items():
        df = price_dfs.get(t)
        if df is None or asof not in df.index:
            print(f"  WARNING: no {field} price for {t} on {asof.date()}; holding basis flat for this leg.")
            total += basis_value_per_slot
            continue
        total += basis_value_per_slot * (df.loc[asof, field] / entry_px)
    return total


def _upsert_equity_row(equity: pd.DataFrame, asof: pd.Timestamp, value: float) -> pd.DataFrame:
    equity = equity[equity["date"] != asof]
    return pd.concat([equity, pd.DataFrame([{"date": asof, "value": value}])], ignore_index=True).sort_values("date")


def _update_spy_benchmark(asof: pd.Timestamp):
    """SPY is stored as raw close (not rebased) - a live append is just
    today's close, no basis-chaining needed. Best-effort: a failure here
    shouldn't block the actual strategy update."""
    try:
        spy = pd.read_csv(SPY_CSV, parse_dates=["date"])
        if asof in spy["date"].values:
            return
        recent_spy = fetch.fetch_prices(["SPY"], start=(asof - pd.Timedelta(days=5)).strftime("%Y-%m-%d"))
        close = recent_spy.get("SPY", pd.DataFrame())
        if asof not in close.index:
            print(f"  WARNING: no SPY close for {asof.date()}; skipping benchmark update.")
            return
        spy = _upsert_equity_row(spy, asof, float(close.loc[asof, "close"]))
        spy.to_csv(SPY_CSV, index=False)
    except Exception as e:
        print(f"  WARNING: SPY benchmark update failed ({e}); continuing without it.")


def main():
    equity, rebal = _load()
    last_period, entry_prices, basis = _last_holding_state(rebal)
    held_tickers = list(entry_prices.keys())

    recent = fetch.fetch_prices(held_tickers, start=(pd.Timestamp.today() - pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
    if not recent:
        print("No fresh price data for currently held tickers; nothing to do today.")
        return

    common_dates = set.intersection(*(set(df.index) for df in recent.values())) if len(recent) == len(held_tickers) else set()
    if not common_dates:
        common_dates = set.union(*(set(df.index) for df in recent.values()))
    asof = max(common_dates)

    _update_spy_benchmark(asof)

    if not equity.empty and asof <= equity["date"].max():
        print(f"Already up to date through {asof.date()}; rebuilding page only.")
        build_page.build()
        return

    asof_period = pd.Period(asof, freq="M")

    if asof_period > last_period:
        print(f"New month detected ({asof_period} > {last_period}) - rebalancing on {asof.date()}.")
        total_at_open = _mark_to_market(recent, entry_prices, basis, "open", asof)

        tickers = universe.get_sp500_tickers()
        lookback_start = (asof.replace(day=1) - pd.DateOffset(months=rank.LOOKBACK_MONTHS)).strftime("%Y-%m-%d")
        print(f"Fetching {len(tickers)} tickers from {lookback_start} for the monthly rescan...")
        bars = fetch.fetch_prices(tickers, start=lookback_start)

        new_tickers = sorted(rank.pick_top_n(bars, as_of_period=asof_period - 1, n=rank.N_HOLD))
        if not new_tickers:
            print("ERROR: ranking produced no eligible picks; leaving prior holdings in place.", file=sys.stderr)
            build_page.build()
            return

        missing = [t for t in new_tickers if asof not in bars.get(t, pd.DataFrame()).index]
        if missing:
            print(f"ERROR: missing today's bar for pick(s) {missing}; aborting this rebalance attempt.", file=sys.stderr)
            build_page.build()
            return

        n = len(new_tickers)
        new_basis = total_at_open / n
        new_entry_prices = {t: bars[t].loc[asof, "open"] for t in new_tickers}
        close_value = sum(new_basis * (bars[t].loc[asof, "close"] / new_entry_prices[t]) for t in new_tickers)

        rebal = pd.concat([rebal, pd.DataFrame([{
            "period": str(asof_period),
            "entry_date": asof.date().isoformat(),
            "holdings": ",".join(new_tickers),
            "entry_prices": ",".join(f"{new_entry_prices[t]:.4f}" for t in new_tickers),
            "basis_value_per_slot": round(new_basis, 6),
        }])], ignore_index=True)
        equity = _upsert_equity_row(equity, asof, close_value)
        print(f"Rebalanced: {','.join(sorted(entry_prices.keys()))} -> {','.join(new_tickers)}")
    else:
        value = _mark_to_market(recent, entry_prices, basis, "close", asof)
        equity = _upsert_equity_row(equity, asof, value)
        print(f"{asof.date()}: portfolio value {value:.2f}")

    equity.to_csv(EQUITY_CSV, index=False)
    rebal.to_csv(REBALANCE_CSV, index=False)
    build_page.build()


if __name__ == "__main__":
    main()
