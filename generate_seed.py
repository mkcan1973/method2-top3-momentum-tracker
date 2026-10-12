"""
One-time, LOCAL ONLY script to bootstrap this tracker's historical data
from the existing, already point-in-time-corrected method2 backtest
(C:\\mark\\scripts\\method2\\top_n_momentum.py, N=3, 6-month lookback).

Not run by the GitHub Action - it depends on method1's local full-history
price database, which never leaves this machine. Produces two seed CSVs
(equity_history.csv, rebalance_log.csv) covering the FULL backtest window
(2010-01 onward - see fetch_sp500_membership_history.py's point-in-time
S&P 500 membership cache) through the last completed backtest month;
rebased to $100 at the earliest date. The tracker page lets viewers pick
any later start year to rebase/slice client-side; the live tracker itself
appends to these same two files going forward using its own independently
fetched (non point-in-time) data.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, r"C:\mark\scripts\method2")

import top_n_momentum as tnm  # noqa: E402

FIRST_MONTH = "2010-01"
OUT_DIR = Path(__file__).parent


def main():
    result = tnm.run(n=3, lookback_months=6, first_month=FIRST_MONTH)
    eq_df = result["equity_curve"].reset_index(drop=True)

    base = eq_df["capital"].iloc[0]
    eq_df["value"] = eq_df["capital"] / base * 100.0
    eq_df[["date", "value"]].to_csv(OUT_DIR / "equity_history.csv", index=False)
    print(f"Wrote equity_history.csv: {len(eq_df)} rows, {eq_df['date'].iloc[0].date()}..{eq_df['date'].iloc[-1].date()}")

    log_df = pd.read_csv(result["log_path"])

    conn = tnm.data_db.connect()
    all_bars = tnm.data_db.load_bars(conn)
    spy_bars = all_bars["SPY"]
    eq_indexed = eq_df.set_index("date")["value"]

    # Stored as raw close (not rebased) - rebasing happens client-side, same as
    # EQUITY_RAW, which also keeps live daily appends trivial (just the day's
    # close, no basis-chaining math needed).
    spy_window = spy_bars.loc[eq_df["date"].iloc[0]:eq_df["date"].iloc[-1], "close"]
    spy_df = spy_window.reset_index()
    spy_df.columns = ["date", "value"]
    spy_df.to_csv(OUT_DIR / "spy_history.csv", index=False)
    print(f"Wrote spy_history.csv: {len(spy_df)} rows, {spy_df['date'].iloc[0].date()}..{spy_df['date'].iloc[-1].date()}")

    entry_dates, entry_prices_col, basis_per_slot_col = [], [], []
    for _, row in log_df.iterrows():
        period = pd.Period(row["period"], freq="M")
        tickers = row["holdings"].split(",")
        month_days = spy_bars.index[spy_bars.index.to_period("M") == period]
        entry_date = month_days[0]
        entry_dates.append(entry_date.date().isoformat())
        prices = [all_bars[t].loc[entry_date, "open"] for t in tickers]
        entry_prices_col.append(",".join(f"{p:.4f}" for p in prices))
        total_value = eq_indexed.loc[entry_date] if entry_date in eq_indexed.index else 100.0
        basis_per_slot_col.append(round(total_value / len(tickers), 6))

    log_df["entry_date"] = entry_dates
    log_df["entry_prices"] = entry_prices_col
    log_df["basis_value_per_slot"] = basis_per_slot_col
    log_df[["period", "entry_date", "holdings", "entry_prices", "basis_value_per_slot"]].to_csv(
        OUT_DIR / "rebalance_log.csv", index=False)
    print(f"Wrote rebalance_log.csv: {len(log_df)} rows, {log_df['period'].iloc[0]}..{log_df['period'].iloc[-1]}")


if __name__ == "__main__":
    main()
