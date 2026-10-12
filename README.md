# Top-3 Momentum Tracker

Live dashboard for a "chase recent winners" strategy: every month, hold the
3 S&P 500 stocks with the best trailing 6-month return, equal-weighted, no
stop loss (the monthly re-rank is the risk control). Research/educational
only - not auto-traded, not investment advice.

Live page: https://mkcan1973.github.io/method2-top3-momentum-tracker/

History before the tracker started running is seeded from a point-in-time-
corrected backtest in `C:\mark\scripts\method2` (`top_n_momentum.py`,
N=3, 6-month lookback) - see that project for the strategy's validation
and known limitations (no train/test split; recent performance has been
concentrated in a handful of semiconductor/AI-memory names).

## How it runs

A GitHub Action (`.github/workflows/run.yml`) runs `run_daily.py` daily
after market close:
- Marks the 3 currently-held tickers to market and appends to
  `equity_history.csv`.
- Once a month, re-ranks the *current* S&P 500 list (no point-in-time
  correction needed for a live, present-tense decision) and rebalances,
  appending a row to `rebalance_log.csv`.
- Rebuilds `index.html` and pushes everything back to `main`.

## Files

- `universe.py` - current S&P 500 constituent list (Wikipedia, 7-day cache).
- `fetch.py` - yfinance batch price fetch + split-corruption guard.
- `rank.py` - trailing 6-month momentum ranking (same definition as the backtest).
- `run_daily.py` - daily driver: mark-to-market + monthly rebalance.
- `build_page.py` - builds `index.html` from the two CSV logs.
- `generate_seed.py` - one-time, local-only bootstrap from the method2 backtest (not run in CI).
