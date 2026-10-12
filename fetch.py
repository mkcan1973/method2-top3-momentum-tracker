"""
Live price fetch helpers (yfinance), ported from method1-tracker's
fetch_stock_data.py batching/column-shape handling and split-guard logic.
This tracker never persists a price database - everything is fetched
fresh each run and only the derived equity_history.csv / rebalance_log.csv
rows are kept.
"""

import pandas as pd
import yfinance as yf

BATCH_SIZE = 50
EXTREME_MOVE_THRESHOLD = 5.0  # 500% in one day anywhere in the fetched window - see fetch_stock_data.py


def _drop_unadjusted_split_rows(ticker: str, df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 2:
        return df
    day_ret = df["Close"].pct_change()
    extreme = (day_ret.abs() > EXTREME_MOVE_THRESHOLD).fillna(False)
    if extreme.any():
        bad_dates = [ts.date() for ts in df.index[extreme]]
        print(f"  WARNING: {ticker} shows an implausible >{EXTREME_MOVE_THRESHOLD * 100:.0f}% "
              f"single-day move on {bad_dates} (likely corrupted/unadjusted split data) "
              f"-- dropping this ticker.")
        return df.iloc[0:0]
    return df


def _download_batch(tickers: list[str], start: str) -> dict:
    data = yf.download(tickers, start=start, auto_adjust=True, progress=False, group_by="ticker")
    if data.empty:
        return {}
    if len(tickers) == 1:
        if isinstance(data.columns, pd.MultiIndex):
            return {tickers[0]: data[tickers[0]]} if tickers[0] in data.columns.get_level_values(0) else {}
        return {tickers[0]: data}
    return {t: data[t] for t in tickers if t in data.columns.get_level_values(0)}


def fetch_prices(tickers: list[str], start: str) -> dict[str, pd.DataFrame]:
    """Returns {ticker: DataFrame[open, close]} indexed by date, auto_adjust=True,
    split-guarded, dropna'd. Missing/delisted tickers are simply absent from the result."""
    out = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        try:
            results = _download_batch(batch, start)
        except Exception as e:
            print(f"  ERROR fetching batch {i // BATCH_SIZE}: {e}")
            continue
        for t in batch:
            df = results.get(t)
            if df is None or df.empty:
                continue
            df = _drop_unadjusted_split_rows(t, df).dropna()
            if df.empty:
                continue
            out[t] = df.rename(columns={"Open": "open", "Close": "close"})[["open", "close"]]
    return out
