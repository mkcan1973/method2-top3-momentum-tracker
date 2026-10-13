# Blended Momentum Tracker

Live dashboard for a 2-sleeve blend, rebalanced to a fixed 50/50 split every
January:
- **Sleeve A (50%)**: one stock, picked every January by the prior calendar
  year's best point-in-time-eligible S&P 500 return, held all year with a
  35% stop-loss (method2's `rotation_backtest.py`, freq="year").
- **Sleeve B (50%)**: the existing top-3, 6-month-lookback momentum
  strategy, rebalanced monthly (method2's `top_n_momentum.py`).

This combo was chosen in `method_combination_analysis.py` /
`plot_best_combo.py` (`C:\mark\scripts\method2`) as the pair of method2
variants giving the most consistent year-by-year returns - 13/13 up-years,
2013-2025, point-in-time corrected S&P 500 membership - rather than just the
highest CAGR. Research/educational only - not auto-traded, not investment
advice. Sleeve A is a concentrated, small-sample, single-stock strategy;
its strong backtested record reflects the specific historical picks it
happened to land on, not a robustly validated edge.

Live page: https://mkcan1973.github.io/method2-top3-momentum-tracker/

History before the tracker started running is seeded from point-in-time-
corrected backtests in `C:\mark\scripts\method2` - see that project for
the strategies' validation and known limitations (no train/test split).

## How it runs

A GitHub Action (`.github/workflows/run.yml`) runs `run_daily.py` daily
after market close:
- Marks both sleeves to market and appends the combined value to
  `equity_history.csv`.
- Monthly (not January): sleeve B re-ranks and rebalances on its own
  running capital; sleeve A is untouched.
- January: combined capital is re-split 50/50; sleeve A picks its new
  stock (current real S&P 500 list - no point-in-time correction needed
  for a live, present-tense decision); sleeve B does its normal monthly
  rebalance on the new 50% basis.
- Sleeve A's 35% stop-loss is checked daily off its own recent price
  window; once triggered it sits in frozen cash for the rest of that year.
- Rebuilds `index.html` and pushes everything back to `main`.

## Files

- `universe.py` - current S&P 500 constituent list (Wikipedia, 7-day cache).
- `fetch.py` - yfinance batch price fetch + split-corruption guard.
- `rank.py` - monthly top-3 momentum ranking + yearly best-performer pick
  (same definitions as the backtests).
- `run_daily.py` - daily driver: both sleeves' mark-to-market, monthly
  sleeve B rebalance, annual sleeve A pick + 50/50 reweight.
- `build_page.py` - builds `index.html` from the three CSV logs
  (`equity_history.csv`, `rebalance_log.csv` for sleeve B, `sleeve_a_log.csv`
  for sleeve A).
- `generate_seed.py` - one-time, local-only bootstrap from the method2
  backtests (not run in CI).
