"""
One-time, LOCAL ONLY backfill: the live tracker didn't actually start
running until 2026-10-12, so sleeve A, sleeve B, and SPY all had a
2026-01 through 2026-09 gap (sleeve A nominally kept "holding" 2025's
pick, PLTR, all the way to October instead of rolling into 2026's pick
on schedule; sleeve B's rebalance_log.csv had those months removed
entirely after they were found to show $0 - see MEMORY.md 2026-10-27).

Now that Jan-Sep 2026 is fully historical, reconstruct it properly and
replace the ENTIRE 2026 portion of equity_history.csv/rebalance_log.csv/
sleeve_a_log.csv/spy_history.csv with a single, internally consistent
computation (rather than trying to algebraically patch the existing,
wrongly-scaled October entries):
  - Sleeve A: one continuous position all year, entered 2026-01-02 like
    every other year (not 2026-10-12), SNDK's real full-year price path
    fetched fresh (not stitched from local DB + live).
  - Sleeve B: Jan-Sep reuses top_n_momentum.run()'s own natural
    continuation (point-in-time corrected, local-DB-based); the October
    rebalance (same AMD/MRNA/MU pick, same entry prices - unchanged)
    gets a freshly-fetched price path Oct 12-today instead of the old
    (wrongly-scaled) daily values.

Run this ONCE; after it, the live GitHub Action just keeps appending
from "today" as usual.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, r"C:\mark\scripts\method2")
import rotation_backtest as rb  # noqa: E402
import top_n_momentum as tnm  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import fetch  # noqa: E402

OUT_DIR = Path(__file__).parent
WEIGHT_A = 0.5
WEIGHT_B = 0.5
STOP_LOSS_PCT = rb.STOP_LOSS_PCT


def simulate_long_from_fresh(df: pd.DataFrame, entry_date: pd.Timestamp):
    """Same stop-loss/mark-to-market logic as rb.simulate_holding_period,
    operating on a freshly-fetched open/close DataFrame instead of the
    local DB, so sleeve A's path is verifiably correct end to end."""
    pb = df.loc[entry_date:]
    entry_price = pb["open"].iloc[0]
    stop_price = entry_price * (1.0 - STOP_LOSS_PCT)
    n = len(pb)
    stop_idx = None
    for i in range(n):
        if pb["close"].iloc[i] <= stop_price:
            stop_idx = i
            break
    stopped_out = stop_idx is not None
    exit_idx = None
    if stopped_out and stop_idx + 1 < n:
        exit_idx = stop_idx + 1
        exit_price = pb["open"].iloc[exit_idx]
    elif stopped_out:
        exit_idx = stop_idx
        exit_price = pb["close"].iloc[exit_idx]
    mult = {}
    for i in range(n):
        d = pb.index[i]
        if exit_idx is not None and i >= exit_idx:
            mult[d] = exit_price / entry_price
        else:
            mult[d] = pb["close"].iloc[i] / entry_price
    return entry_price, stopped_out, pd.Series(mult)


def main():
    equity = pd.read_csv(OUT_DIR / "equity_history.csv", parse_dates=["date"])
    rebal = pd.read_csv(OUT_DIR / "rebalance_log.csv")
    sleeve_a = pd.read_csv(OUT_DIR / "sleeve_a_log.csv")
    spy = pd.read_csv(OUT_DIR / "spy_history.csv", parse_dates=["date"])

    combined_start = float(equity[equity["date"] == "2025-12-31"]["value"].iloc[0])
    print(f"Combined value at 2025-12-31: {combined_start:.6f}")
    cap_a_start = combined_start * WEIGHT_A
    cap_b_start = combined_start * WEIGHT_B

    oct_row = rebal.iloc[-1]
    assert oct_row["period"] == "2026-10"
    oct_date = pd.Timestamp(oct_row["entry_date"])
    oct_tickers = oct_row["holdings"].split(",")
    oct_entry_prices = dict(zip(oct_tickers, (float(p) for p in oct_row["entry_prices"].split(","))))
    sndk_pick = sleeve_a[sleeve_a["year"] == 2026].iloc[0]["ticker"]
    print(f"Sleeve A 2026 pick: {sndk_pick}  Sleeve B October pick: {oct_tickers} entered {oct_date.date()}")

    conn = rb.data_db.connect()
    all_bars = rb.data_db.load_bars(conn)
    spy_bars = all_bars["SPY"]
    jan2 = spy_bars.index[spy_bars.index.to_period("M") == pd.Period("2026-01", freq="M")][0]
    today = pd.Timestamp.today().normalize()

    # --- Sleeve A: SNDK, fresh full path Jan2-today ---
    sndk_df = fetch.fetch_prices([sndk_pick], start=(jan2 - pd.Timedelta(days=3)).strftime("%Y-%m-%d"))[sndk_pick]
    a_entry_price, a_stopped, a_mult = simulate_long_from_fresh(sndk_df, jan2)
    print(f"Sleeve A: {sndk_pick} entered {jan2.date()} @ {a_entry_price:.2f}, stopped_out={a_stopped}, "
          f"{len(a_mult)} trading days through {a_mult.index[-1].date()}")

    # --- Sleeve B: Jan-Sep via top_n_momentum's own natural continuation ---
    result_b = tnm.run(n=3, lookback_months=6, first_month="2013-01")
    eq_b_full = result_b["equity_curve"].set_index("date")["capital"]
    log_b_full = pd.read_csv(result_b["log_path"])
    log_b_2026 = log_b_full[(log_b_full["period"] >= "2026-01") & (log_b_full["period"] <= "2026-09")].reset_index(drop=True)
    jan2_capital = eq_b_full.loc[jan2]
    b_mult_jan_sep = (eq_b_full / jan2_capital)
    b_mult_jan_sep = b_mult_jan_sep[(b_mult_jan_sep.index >= jan2) & (b_mult_jan_sep.index <= "2026-09-30")]
    print(f"Sleeve B natural continuation: {len(log_b_2026)} monthly picks, "
          f"{len(b_mult_jan_sep)} trading days Jan-Sep")

    # --- Sleeve B monthly log rows, Jan-Sep, basis = cap_b_start * b_mult at each month's entry ---
    new_sleeve_b_rows = []
    sep_entry_date, sep_entry_prices, sep_basis_per_slot = None, None, None
    for _, row in log_b_2026.iterrows():
        period = pd.Period(row["period"], freq="M")
        tickers = row["holdings"].split(",")
        month_days = spy_bars.index[spy_bars.index.to_period("M") == period]
        entry_date = month_days[0]
        prices = {t: all_bars[t].loc[entry_date, "open"] for t in tickers}
        basis_total = cap_b_start * b_mult_jan_sep.loc[entry_date]
        new_sleeve_b_rows.append({
            "period": row["period"], "entry_date": entry_date.date().isoformat(),
            "holdings": row["holdings"],
            "entry_prices": ",".join(f"{prices[t]:.4f}" for t in tickers),
            "basis_value_per_slot": round(basis_total / len(tickers), 6),
        })
        if row["period"] == "2026-09":
            sep_entry_date, sep_entry_prices = entry_date, prices
            sep_basis_per_slot = basis_total / len(tickers)

    # --- Bridge: September's position marked to October 12's open (no double-counting - uses
    #     September's own entry basis/prices directly against Oct 12, not via Sept 30) ---
    sep_tickers = list(sep_entry_prices.keys())
    bridge_prices = fetch.fetch_prices(sep_tickers, start=(sep_entry_date).strftime("%Y-%m-%d"))
    total_at_oct_open = sum(
        sep_basis_per_slot * (bridge_prices[t].loc[oct_date, "open"] / sep_entry_prices[t])
        for t in sep_tickers
    )
    corrected_oct_basis_per_slot = round(total_at_oct_open / len(oct_tickers), 6)
    print(f"September basis/slot: {sep_basis_per_slot:.6f} -> total at Oct 12 open: {total_at_oct_open:.6f} "
          f"-> corrected October basis/slot: {corrected_oct_basis_per_slot} (was {oct_row['basis_value_per_slot']})")

    # --- Sleeve B, Oct 12-today: fresh path for AMD/MRNA/MU off the corrected basis ---
    oct_prices = fetch.fetch_prices(oct_tickers, start=(oct_date - pd.Timedelta(days=3)).strftime("%Y-%m-%d"))
    oct_dates = sorted(set.intersection(*(set(oct_prices[t].index) for t in oct_tickers)))
    oct_dates = [d for d in oct_dates if d >= oct_date]
    b_value_oct = {d: sum(corrected_oct_basis_per_slot * (oct_prices[t].loc[d, "close"] / oct_entry_prices[t]) for t in oct_tickers)
                   for d in oct_dates}

    # --- Sleeve B, Oct 1-11: still holding September's pick, marked daily to bridge_prices
    #     (the same fetch already used for the Sept->Oct transition) ---
    gap_dates = sorted(set.intersection(*(set(bridge_prices[t].index) for t in sep_tickers))
                        & {d for d in bridge_prices[sep_tickers[0]].index if d > sep_entry_date and d < oct_date})
    b_value_gap = {d: sum(sep_basis_per_slot * (bridge_prices[t].loc[d, "close"] / sep_entry_prices[t]) for t in sep_tickers)
                   for d in gap_dates}
    print(f"Sleeve B Oct 1-11 gap filled: {len(b_value_gap)} days")

    # --- Combined daily series: Jan2-Sep30 (natural), Oct1-11 (gap fill), Oct12-today (sleeve B's new position) ---
    combined_rows = []
    for d in b_mult_jan_sep.index:
        a_val = cap_a_start * a_mult.get(d, a_mult.iloc[0])
        b_val = cap_b_start * b_mult_jan_sep[d]
        combined_rows.append((d, a_val + b_val))
    for d, b_val in {**b_value_gap, **b_value_oct}.items():
        a_val = cap_a_start * a_mult.get(d)
        if a_val is None:
            continue  # sleeve A's fetched path doesn't cover this date (weekend/holiday mismatch) - skip, not interpolate
        combined_rows.append((d, a_val + b_val))

    new_equity_2026 = pd.DataFrame(combined_rows, columns=["date", "value"]).drop_duplicates("date").sort_values("date")
    print(f"Backfilled {len(new_equity_2026)} combined daily rows, "
          f"{new_equity_2026['date'].iloc[0].date()}..{new_equity_2026['date'].iloc[-1].date()}")

    # --- Sleeve A's single 2026 row ---
    a_last_date = a_mult.index[-1]
    sleeve_a = sleeve_a[sleeve_a["year"] != 2026]
    sleeve_a_new_row = {
        "year": 2026, "ticker": sndk_pick, "entry_date": jan2.date().isoformat(),
        "entry_price": a_entry_price, "exit_date": "", "exit_price": "",
        "stopped_out": a_stopped, "basis_value": round(cap_a_start, 6),
    }
    if a_stopped:
        exit_px = a_mult.iloc[-1] * a_entry_price  # frozen value's implied price, for the record
        sleeve_a_new_row["exit_price"] = round(float(exit_px), 2)
    sleeve_a = pd.concat([sleeve_a, pd.DataFrame([sleeve_a_new_row])], ignore_index=True)

    # --- Rewrite rebalance_log.csv: 2025-and-earlier unchanged, Jan-Sep backfilled, Oct basis corrected ---
    rebal = rebal[rebal["period"] < "2026-01"]
    rebal = pd.concat([rebal, pd.DataFrame(new_sleeve_b_rows)], ignore_index=True)
    rebal = pd.concat([rebal, pd.DataFrame([{
        "period": "2026-10", "entry_date": oct_date.date().isoformat(),
        "holdings": oct_row["holdings"], "entry_prices": oct_row["entry_prices"],
        "basis_value_per_slot": corrected_oct_basis_per_slot,
    }])], ignore_index=True)
    rebal.to_csv(OUT_DIR / "rebalance_log.csv", index=False)
    sleeve_a.to_csv(OUT_DIR / "sleeve_a_log.csv", index=False)
    print(f"Wrote rebalance_log.csv ({len(rebal)} rows) and sleeve_a_log.csv ({len(sleeve_a)} rows)")

    # --- Rewrite equity_history.csv: 2025-and-earlier unchanged, entire 2026 portion replaced ---
    equity_2025 = equity[equity["date"] <= "2025-12-31"]
    new_equity = pd.concat([equity_2025, new_equity_2026], ignore_index=True).drop_duplicates("date").sort_values("date")
    new_equity.to_csv(OUT_DIR / "equity_history.csv", index=False)
    print(f"Wrote equity_history.csv ({len(new_equity)} rows, "
          f"{new_equity['date'].iloc[0].date()}..{new_equity['date'].iloc[-1].date()})")

    # --- SPY: fill the raw-close gap, Jan2-today ---
    spy_window = spy_bars.loc[jan2:oct_date - pd.Timedelta(days=1), "close"]
    spy_fill = spy_window.reset_index()
    spy_fill.columns = ["date", "value"]
    new_spy = pd.concat([spy, spy_fill], ignore_index=True).drop_duplicates("date").sort_values("date")
    new_spy.to_csv(OUT_DIR / "spy_history.csv", index=False)
    print(f"Wrote spy_history.csv ({len(new_spy)} rows)")


if __name__ == "__main__":
    main()
