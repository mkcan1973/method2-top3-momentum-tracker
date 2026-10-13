"""
Trailing 6-month momentum ranking - same definition as method2's
rotation_backtest.compute_period_return_table + diversified_rotation.
trailing_n_month_table (calendar-month close-to-close returns, compounded
over the trailing window), kept consistent so the live picks are computed
the same way the backtested history (rebalance_log.csv's seed rows) was.
"""

import numpy as np
import pandas as pd

MIN_SESSIONS_MONTH = 15
LOOKBACK_MONTHS = 6
N_HOLD = 3
MIN_SESSIONS_YEAR = 200
STOP_LOSS_PCT = 0.35


def month_return_table(bars_by_ticker: dict[str, pd.DataFrame]) -> pd.DataFrame:
    columns = {}
    for t, bars in bars_by_ticker.items():
        if bars.empty:
            continue
        per = bars.index.to_period("M")
        g = bars.groupby(per)
        first_close = g["close"].first()
        last_close = g["close"].last()
        counts = g["close"].size()
        ret = (last_close / first_close - 1.0).where(counts >= MIN_SESSIONS_MONTH)
        columns[t] = ret
    return pd.DataFrame(columns)


def trailing_return(ret_table: pd.DataFrame, as_of_period: pd.Period) -> pd.Series:
    """Compounded trailing-LOOKBACK_MONTHS return ending at `as_of_period`,
    NaN for tickers missing a qualifying return in any of those months."""
    window = ret_table.loc[:as_of_period].tail(LOOKBACK_MONTHS)
    if len(window) < LOOKBACK_MONTHS:
        return pd.Series(dtype=float)
    log_ret = np.log1p(window)
    return np.expm1(log_ret.sum())


def pick_top_n(bars_by_ticker: dict[str, pd.DataFrame], as_of_period: pd.Period, n: int = N_HOLD) -> list[str]:
    ret_table = month_return_table(bars_by_ticker)
    trail = trailing_return(ret_table, as_of_period).dropna()
    return trail.sort_values(ascending=False).head(n).index.tolist()


def pick_best_year(bars_by_ticker: dict[str, pd.DataFrame], year: int) -> str | None:
    """Single best full-calendar-year close-to-close return - sleeve A's
    annual pick, same definition as method2's rotation_backtest.py
    (freq="year")."""
    best_ticker, best_ret = None, None
    for t, bars in bars_by_ticker.items():
        yb = bars[bars.index.year == year]
        if len(yb) < MIN_SESSIONS_YEAR:
            continue
        ret = yb["close"].iloc[-1] / yb["close"].iloc[0] - 1.0
        if best_ret is None or ret > best_ret:
            best_ticker, best_ret = t, ret
    return best_ticker
