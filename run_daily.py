"""
Daily driver for the blended tracker: 50% sleeve A (one stock, picked
every January by the prior calendar year's best point-in-time-eligible
S&P 500 return, 35% stop-loss) + 50% sleeve B (the existing top-3,
6-month-lookback momentum strategy, rebalanced monthly), rebalanced to
that 50/50 split every January. This combo was chosen in
C:\\mark\\scripts\\method2\\method_combination_analysis.py as the pair
giving the most consistent year-by-year returns (13/13 up-years,
2013-2025, point-in-time corrected) among all the method2 variants.

Every run: marks both sleeves to market and appends today's combined
value to equity_history.csv.
  - Monthly (not January): sleeve B re-ranks and rebalances on its own
    50%-of-combined basis; sleeve A is untouched.
  - January (new year vs. sleeve_a_log.csv's last row - naturally
    self-retrying if a run fails on the actual 1st, same as the old
    monthly-only logic was): combined capital is re-split 50/50, sleeve A
    picks its new stock, sleeve B does its normal monthly rebalance on
    the new 50% basis.
  - Sleeve A's stop-loss is checked daily off its own recent price
    window (no persisted "pending" state needed) and, once triggered,
    sleeve A sits in frozen cash for the rest of that year.
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
REBALANCE_CSV = OUT_DIR / "rebalance_log.csv"          # sleeve B (top3, monthly)
SLEEVE_A_CSV = OUT_DIR / "sleeve_a_log.csv"             # sleeve A (yearly single-stock)
SPY_CSV = OUT_DIR / "spy_history.csv"

WEIGHT_A = 0.5
WEIGHT_B = 0.5


def _load():
    equity = pd.read_csv(EQUITY_CSV, parse_dates=["date"])
    rebal = pd.read_csv(REBALANCE_CSV)
    sleeve_a = pd.read_csv(SLEEVE_A_CSV)
    return equity, rebal, sleeve_a


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


def _upsert_row(df: pd.DataFrame, key_col: str, key_val, row: dict) -> pd.DataFrame:
    df = df[df[key_col] != key_val]
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True).sort_values(key_col)


def _mark_sleeve_a(sleeve_a: pd.DataFrame, price_df: pd.DataFrame, asof: pd.Timestamp) -> tuple[float, pd.DataFrame]:
    """Returns (today's sleeve A value, possibly-updated sleeve_a log)."""
    current = sleeve_a.iloc[-1].to_dict()
    entry_price = float(current["entry_price"])
    basis_value = float(current["basis_value"])

    if bool(current["stopped_out"]):
        exit_price = float(current["exit_price"])
        return basis_value * (exit_price / entry_price), sleeve_a

    entry_date = pd.Timestamp(current["entry_date"])
    window = price_df.loc[entry_date:asof] if price_df is not None else pd.DataFrame()
    if window.empty:
        print(f"  WARNING: no price window for sleeve A ticker {current['ticker']}; holding basis flat.")
        return basis_value, sleeve_a

    stop_price = entry_price * (1.0 - rank.STOP_LOSS_PCT)
    breach = window.index[window["close"] <= stop_price]
    if len(breach):
        breach_date = breach[0]
        after = window.loc[breach_date:].index
        if len(after) > 1:
            exit_date = after[1]
            exit_price = float(window.loc[exit_date, "open"])
            current["exit_date"] = exit_date.date().isoformat()
            current["exit_price"] = exit_price
            current["stopped_out"] = True
            sleeve_a = _upsert_row(sleeve_a, "year", current["year"], current)
            print(f"  Sleeve A stopped out: {current['ticker']} exited {exit_date.date()} @ {exit_price:.2f}")
            return basis_value * (exit_price / entry_price), sleeve_a
        else:
            px = float(window["close"].iloc[-1])
            return basis_value * (px / entry_price), sleeve_a

    px = float(window.loc[asof, "close"]) if asof in window.index else float(window["close"].iloc[-1])
    return basis_value * (px / entry_price), sleeve_a


def _rebalance_sleeve_b_only(rebal, recent, entry_prices, basis, asof, asof_period):
    total_at_open = _mark_to_market(recent, entry_prices, basis, "open", asof)
    tickers = universe.get_sp500_tickers()
    lookback_start = (asof.replace(day=1) - pd.DateOffset(months=rank.LOOKBACK_MONTHS)).strftime("%Y-%m-%d")
    print(f"Fetching {len(tickers)} tickers from {lookback_start} for the monthly rescan...")
    bars = fetch.fetch_prices(tickers, start=lookback_start)
    return _enter_sleeve_b(rebal, bars, asof, asof_period, total_at_open)


def _enter_sleeve_b(rebal, bars, asof, asof_period, total_value):
    new_tickers = sorted(rank.pick_top_n(bars, as_of_period=asof_period - 1, n=rank.N_HOLD))
    if not new_tickers:
        print("ERROR: sleeve B ranking produced no eligible picks; leaving prior holdings in place.", file=sys.stderr)
        return rebal, None
    missing = [t for t in new_tickers if asof not in bars.get(t, pd.DataFrame()).index]
    if missing:
        print(f"ERROR: missing today's bar for sleeve B pick(s) {missing}; aborting.", file=sys.stderr)
        return rebal, None

    n = len(new_tickers)
    new_basis = total_value / n
    new_entry_prices = {t: bars[t].loc[asof, "open"] for t in new_tickers}
    close_value = sum(new_basis * (bars[t].loc[asof, "close"] / new_entry_prices[t]) for t in new_tickers)

    rebal = pd.concat([rebal, pd.DataFrame([{
        "period": str(asof_period),
        "entry_date": asof.date().isoformat(),
        "holdings": ",".join(new_tickers),
        "entry_prices": ",".join(f"{new_entry_prices[t]:.4f}" for t in new_tickers),
        "basis_value_per_slot": round(new_basis, 6),
    }])], ignore_index=True)
    return rebal, close_value


def _update_spy_benchmark(asof: pd.Timestamp):
    try:
        spy = pd.read_csv(SPY_CSV, parse_dates=["date"])
        if asof in spy["date"].values:
            return
        recent_spy = fetch.fetch_prices(["SPY"], start=(asof - pd.Timedelta(days=5)).strftime("%Y-%m-%d"))
        close = recent_spy.get("SPY", pd.DataFrame())
        if asof not in close.index:
            print(f"  WARNING: no SPY close for {asof.date()}; skipping benchmark update.")
            return
        spy = spy[spy["date"] != asof]
        spy = pd.concat([spy, pd.DataFrame([{"date": asof, "value": float(close.loc[asof, "close"])}])], ignore_index=True).sort_values("date")
        spy.to_csv(SPY_CSV, index=False)
    except Exception as e:
        print(f"  WARNING: SPY benchmark update failed ({e}); continuing without it.")


def main():
    equity, rebal, sleeve_a = _load()
    last_period, entry_prices_b, basis_b = _last_holding_state(rebal)
    sleeve_a_current = sleeve_a.iloc[-1]
    sleeve_a_ticker = sleeve_a_current["ticker"]
    sleeve_a_year = int(sleeve_a_current["year"])

    held_tickers = list(entry_prices_b.keys())
    fetch_tickers = list(dict.fromkeys(held_tickers + [sleeve_a_ticker]))
    recent = fetch.fetch_prices(fetch_tickers, start=(pd.Timestamp.today() - pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
    if not recent:
        print("No fresh price data; nothing to do today.")
        return

    held_dfs = {t: recent[t] for t in held_tickers if t in recent}
    common_dates = set.intersection(*(set(df.index) for df in held_dfs.values())) if len(held_dfs) == len(held_tickers) else set()
    if not common_dates:
        common_dates = set.union(*(set(df.index) for df in recent.values()))
    asof = max(common_dates)

    _update_spy_benchmark(asof)

    if not equity.empty and asof <= equity["date"].max():
        print(f"Already up to date through {asof.date()}; rebuilding page only.")
        build_page.build()
        return

    asof_period = pd.Period(asof, freq="M")

    if asof.year > sleeve_a_year:
        print(f"New year detected ({asof.year} > {sleeve_a_year}) - annual 50/50 rebalance on {asof.date()}.")
        old_row = sleeve_a.iloc[-1]
        sleeve_a_ticker_df = recent.get(sleeve_a_ticker)
        if bool(old_row["stopped_out"]):
            sleeve_a_value_at_open = float(old_row["basis_value"]) * (float(old_row["exit_price"]) / float(old_row["entry_price"]))
        elif sleeve_a_ticker_df is not None and asof in sleeve_a_ticker_df.index:
            sleeve_a_value_at_open = float(old_row["basis_value"]) * (sleeve_a_ticker_df.loc[asof, "open"] / float(old_row["entry_price"]))
        else:
            print(f"  WARNING: no open price for outgoing sleeve A ticker {sleeve_a_ticker}; holding basis flat.")
            sleeve_a_value_at_open = float(old_row["basis_value"])

        sleeve_b_value_at_open = _mark_to_market(recent, entry_prices_b, basis_b, "open", asof)
        combined_at_open = sleeve_a_value_at_open + sleeve_b_value_at_open

        prior_year = asof.year - 1
        universe_tickers = universe.get_sp500_tickers()
        year_start = f"{prior_year}-01-01"
        print(f"Fetching {len(universe_tickers)} tickers from {year_start} for the annual sleeve A pick...")
        year_bars = fetch.fetch_prices(universe_tickers, start=year_start)
        pick = rank.pick_best_year(year_bars, prior_year)
        if pick is None or asof not in year_bars.get(pick, pd.DataFrame()).index:
            print("ERROR: sleeve A annual pick failed; leaving prior state in place.", file=sys.stderr)
            build_page.build()
            return

        new_sleeve_a_basis = combined_at_open * WEIGHT_A
        entry_price_a = float(year_bars[pick].loc[asof, "open"])
        close_price_a = float(year_bars[pick].loc[asof, "close"])
        sleeve_a_close_value = new_sleeve_a_basis * (close_price_a / entry_price_a)

        sleeve_a = pd.concat([sleeve_a, pd.DataFrame([{
            "year": asof.year, "ticker": pick, "entry_date": asof.date().isoformat(),
            "entry_price": entry_price_a, "exit_date": "", "exit_price": "",
            "stopped_out": False, "basis_value": round(new_sleeve_a_basis, 6),
        }])], ignore_index=True)

        new_sleeve_b_total = combined_at_open * WEIGHT_B
        tickers_b = universe.get_sp500_tickers()
        lookback_start = (asof.replace(day=1) - pd.DateOffset(months=rank.LOOKBACK_MONTHS)).strftime("%Y-%m-%d")
        bars_b = fetch.fetch_prices(tickers_b, start=lookback_start)
        rebal, sleeve_b_close_value = _enter_sleeve_b(rebal, bars_b, asof, asof_period, new_sleeve_b_total)
        if sleeve_b_close_value is None:
            print("ERROR: sleeve B entry failed during annual rebalance.", file=sys.stderr)
            build_page.build()
            return

        combined_close = sleeve_a_close_value + sleeve_b_close_value
        print(f"Annual rebalance done: sleeve A -> {pick} (${new_sleeve_a_basis:,.2f}), "
              f"sleeve B -> {rebal.iloc[-1]['holdings']} (${new_sleeve_b_total:,.2f})")

    elif asof_period > last_period:
        print(f"New month detected ({asof_period} > {last_period}) - sleeve B monthly rebalance on {asof.date()}.")
        rebal, sleeve_b_close_value = _rebalance_sleeve_b_only(rebal, recent, entry_prices_b, basis_b, asof, asof_period)
        if sleeve_b_close_value is None:
            build_page.build()
            return
        sleeve_a_close_value, sleeve_a = _mark_sleeve_a(sleeve_a, recent.get(sleeve_a_ticker), asof)
        combined_close = sleeve_a_close_value + sleeve_b_close_value

    else:
        sleeve_b_close_value = _mark_to_market(recent, entry_prices_b, basis_b, "close", asof)
        sleeve_a_close_value, sleeve_a = _mark_sleeve_a(sleeve_a, recent.get(sleeve_a_ticker), asof)
        combined_close = sleeve_a_close_value + sleeve_b_close_value
        print(f"{asof.date()}: sleeve A ${sleeve_a_close_value:,.2f} + sleeve B ${sleeve_b_close_value:,.2f} = ${combined_close:,.2f}")

    equity = equity[equity["date"] != asof]
    equity = pd.concat([equity, pd.DataFrame([{"date": asof, "value": combined_close}])], ignore_index=True).sort_values("date")

    equity.to_csv(EQUITY_CSV, index=False)
    rebal.to_csv(REBALANCE_CSV, index=False)
    sleeve_a.to_csv(SLEEVE_A_CSV, index=False)
    build_page.build()


if __name__ == "__main__":
    main()
