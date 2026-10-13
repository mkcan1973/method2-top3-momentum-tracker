"""
One-time, LOCAL ONLY script to bootstrap this tracker's historical data.

The tracker now runs a TWO-SLEEVE blend, 50/50, rebalanced to that split
every January:
  - Sleeve A ("yearly"): one stock, picked each January by the prior
    calendar year's best point-in-time-eligible S&P 500 return, held all
    year with a 35% stop-loss (method2's rotation_backtest.py, freq="year",
    universe="sp500_pointintime").
  - Sleeve B ("top3"): the existing top-3, 6-month-lookback momentum
    strategy, rebalanced monthly (method2's top_n_momentum.py).

This choice came from method_combination_analysis.py / plot_best_combo.py
in C:\\mark\\scripts\\method2 - of all 2-method blends tried, 50% yearly /
50% top3 gave the most consistent year-by-year returns (13/13 up-years,
2013-2025, point-in-time corrected).

Seeds cover 2013-01 onward (sleeve A's first valid pick year - it needs
2012 as a full prior-year signal, same constraint rotation_backtest.py's
"year" freq has always had, not parameterized the way top_n_momentum.py's
first_month was). Produces:
  - equity_history.csv: combined blended daily value, rebased to $100.
  - sleeve_a_log.csv: one row per year (pick, entry/exit, stop info).
  - rebalance_log.csv: sleeve B's monthly picks (same schema the live
    tracker already used when it tracked top3 alone), with each month's
    basis_value_per_slot rescaled to reflect the 50% annual allocation.
  - spy_history.csv: unchanged, independent of strategy choice.

Not run by the GitHub Action - depends on method1's local full-history
price database, which never leaves this machine.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, r"C:\mark\scripts\method2")

import rotation_backtest as rb  # noqa: E402
import top_n_momentum as tnm  # noqa: E402

WEIGHT_A = 0.5  # yearly sleeve
WEIGHT_B = 0.5  # top3 sleeve
FIRST_YEAR = 2013
OUT_DIR = Path(__file__).parent


def rebase_year_start(eq_df: pd.DataFrame, year: int) -> pd.DataFrame:
    sub = eq_df[eq_df["date"].dt.year == year].copy()
    sub["mult"] = sub["capital"] / sub["capital"].iloc[0]
    return sub


def main():
    print("Running yearly sleeve (point-in-time)...")
    result_a = rb.run("sp500_pointintime", "year", "pit_yearly")
    eq_a = result_a["equity_curve"]
    log_a = pd.read_csv(result_a["log_path"])

    print("Running top3 sleeve, 6mo lookback (point-in-time)...")
    result_b = tnm.run(n=3, lookback_months=6, first_month=f"{FIRST_YEAR}-01")
    eq_b = result_b["equity_curve"]
    log_b = pd.read_csv(result_b["log_path"])

    conn = tnm.data_db.connect()
    all_bars = tnm.data_db.load_bars(conn)
    years = list(range(FIRST_YEAR, log_a["period"].max() + 1))

    combined_rows = []
    sleeve_a_basis_by_year = {}   # year -> combined capital * WEIGHT_A at that year's first trading day
    sleeve_b_rescale_by_year = {}  # year -> factor applied to sleeve B's own-standalone basis that year
    capital = 100.0

    for y in years:
        ya = rebase_year_start(eq_a, y)
        yb = rebase_year_start(eq_b, y)
        if ya.empty or yb.empty:
            continue
        cap_a_start = capital * WEIGHT_A
        cap_b_start = capital * WEIGHT_B
        sleeve_a_basis_by_year[y] = cap_a_start
        sleeve_b_rescale_by_year[y] = cap_b_start / yb["capital"].iloc[0]

        dates = sorted(set(ya["date"]) | set(yb["date"]))
        mult_a = ya.set_index("date")["mult"].reindex(dates).ffill().bfill()
        mult_b = yb.set_index("date")["mult"].reindex(dates).ffill().bfill()
        for d in dates:
            combined_rows.append((d, cap_a_start * mult_a[d] + cap_b_start * mult_b[d]))

        capital = cap_a_start * mult_a.iloc[-1] + cap_b_start * mult_b.iloc[-1]

    combined = pd.DataFrame(combined_rows, columns=["date", "capital"]).drop_duplicates("date").sort_values("date")
    base = combined["capital"].iloc[0]
    combined["value"] = combined["capital"] / base * 100.0
    combined[["date", "value"]].to_csv(OUT_DIR / "equity_history.csv", index=False)
    print(f"Wrote equity_history.csv: {len(combined)} rows, {combined['date'].iloc[0].date()}..{combined['date'].iloc[-1].date()}")

    rebase_factor = 100.0 / base  # same units as equity_history.csv's "value"

    # --- Sleeve A log: one row per year ---
    log_a = log_a[log_a["period"].isin(years)].reset_index(drop=True)
    log_a["basis_value"] = log_a["period"].map(sleeve_a_basis_by_year).mul(rebase_factor).round(6)
    log_a_out = log_a[["period", "pick", "entry_date", "entry_price", "exit_date", "exit_price",
                        "stopped_out", "basis_value"]].rename(columns={"period": "year", "pick": "ticker"})
    log_a_out.to_csv(OUT_DIR / "sleeve_a_log.csv", index=False)
    print(f"Wrote sleeve_a_log.csv: {len(log_a_out)} rows")

    # --- Sleeve B log: one row per month, basis rescaled to the 50% annual allocation ---
    log_b = log_b[log_b["period"] >= f"{FIRST_YEAR}-01"].reset_index(drop=True)
    spy_bars = all_bars["SPY"]
    entry_dates, entry_prices_col, basis_per_slot_col = [], [], []
    for _, row in log_b.iterrows():
        period = pd.Period(row["period"], freq="M")
        tickers = row["holdings"].split(",")
        month_days = spy_bars.index[spy_bars.index.to_period("M") == period]
        entry_date = month_days[0]
        entry_dates.append(entry_date.date().isoformat())
        prices = [all_bars[t].loc[entry_date, "open"] for t in tickers]
        entry_prices_col.append(",".join(f"{p:.4f}" for p in prices))
        rescale = sleeve_b_rescale_by_year.get(period.year, 1.0) * rebase_factor
        basis_total = row["total_value"] * rescale
        basis_per_slot_col.append(round(basis_total / len(tickers), 6))

    log_b["entry_date"] = entry_dates
    log_b["entry_prices"] = entry_prices_col
    log_b["basis_value_per_slot"] = basis_per_slot_col
    log_b[["period", "entry_date", "holdings", "entry_prices", "basis_value_per_slot"]].to_csv(
        OUT_DIR / "rebalance_log.csv", index=False)
    print(f"Wrote rebalance_log.csv: {len(log_b)} rows, {log_b['period'].iloc[0]}..{log_b['period'].iloc[-1]}")

    # --- SPY benchmark (unchanged logic, just aligned to the new date range) ---
    spy_window = spy_bars.loc[combined["date"].iloc[0]:combined["date"].iloc[-1], "close"]
    spy_df = spy_window.reset_index()
    spy_df.columns = ["date", "value"]
    spy_df.to_csv(OUT_DIR / "spy_history.csv", index=False)
    print(f"Wrote spy_history.csv: {len(spy_df)} rows, {spy_df['date'].iloc[0].date()}..{spy_df['date'].iloc[-1].date()}")


if __name__ == "__main__":
    main()
