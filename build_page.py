"""
Builds the single static index.html dashboard - inline JSON + hand-rolled
SVG chart, no client-side fetch and no charting library, same
no-dependency approach method1-tracker's web_summary.py uses.
"""

import json
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).parent
EQUITY_CSV = OUT_DIR / "equity_history.csv"
REBALANCE_CSV = OUT_DIR / "rebalance_log.csv"
OUT_HTML = OUT_DIR / "index.html"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Top-3 Momentum Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg-page: #f6f7f9; --bg-panel: #ffffff; --ink-1: #16181d; --ink-2: #555b66;
  --border: #e3e5e9; --accent: #2a66f0; --up: #1a8a4a; --down: #d1402f;
  --chip-bg: #eef2fd;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg-page: #14161a; --bg-panel: #1c1f26; --ink-1: #eef0f3; --ink-2: #a3a9b3;
    --border: #2d313a; --accent: #6f9bff; --up: #38c172; --down: #ff6b5e;
    --chip-bg: #202845;
  }
}
:root[data-theme="dark"] {
  --bg-page: #14161a; --bg-panel: #1c1f26; --ink-1: #eef0f3; --ink-2: #a3a9b3;
  --border: #2d313a; --accent: #6f9bff; --up: #38c172; --down: #ff6b5e;
  --chip-bg: #202845;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg-page); color: var(--ink-1);
  font-family: "IBM Plex Sans", system-ui, sans-serif;
}
.wrap { max-width: 960px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 1.4rem; margin: 0 0 2px; }
.sub { color: var(--ink-2); font-size: 0.9rem; margin: 0 0 20px; }
.panel {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px 20px; margin-bottom: 20px;
}
.panel h2 { font-size: 1rem; margin: 0 0 12px; }
.activity-row { display: flex; gap: 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 0.92rem; }
.activity-row:last-child { border-bottom: none; }
.activity-date { font-family: "IBM Plex Mono", monospace; color: var(--ink-2); min-width: 92px; }
.chip { display: inline-block; padding: 1px 7px; border-radius: 6px; background: var(--chip-bg); font-family: "IBM Plex Mono", monospace; font-size: 0.85rem; margin: 0 2px; }
.chip.sold { color: var(--down); }
.chip.bought { color: var(--up); }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--border); }
th { color: var(--ink-2); font-weight: 500; }
td.num, th.num { text-align: right; font-family: "IBM Plex Mono", monospace; }
.tickers { font-family: "IBM Plex Mono", monospace; }
svg text { fill: var(--ink-2); font-family: "IBM Plex Mono", monospace; font-size: 10px; }
#chart-tooltip {
  position: absolute; display: none; background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 8px; font-size: 0.8rem; font-family: "IBM Plex Mono", monospace;
  pointer-events: none; color: var(--ink-1);
}
footer { color: var(--ink-2); font-size: 0.78rem; margin-top: 24px; line-height: 1.5; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Top-3 Momentum Tracker</h1>
  <p class="sub">As of __AS_OF__ &middot; $100 rebased at 2025-01-02 &middot; monthly rebalance, equal-weight top 3 of the S&amp;P 500 by trailing 6-month return</p>

  <div class="panel">
    <h2>Recent activity</h2>
    __ACTIVITY_HTML__
  </div>

  <div class="panel">
    <h2>Equity curve</h2>
    <div style="position:relative;">
      <svg id="chart" viewBox="0 0 1040 300" width="100%" style="overflow:visible;"></svg>
      <div id="chart-tooltip"></div>
    </div>
  </div>

  <div class="panel">
    <h2>Monthly holdings</h2>
    <table>
      <thead><tr><th>Month</th><th>Rebalance date</th><th class="tickers">Holdings</th><th class="num">Value ($100 base)</th></tr></thead>
      <tbody>__TABLE_ROWS__</tbody>
    </table>
  </div>

  <footer>
    Research/educational tracker only - not auto-traded, not investment advice. Holdings from 2025-01 through
    the method2 backtest's last completed month come from a point-in-time-corrected historical backtest
    (C:\\mark\\scripts\\method2); everything after that is computed live, monthly, against the S&amp;P 500's
    actual current constituent list. No transaction costs or taxes modeled. See the method2 project writeup
    for the strategy's known limitations (no train/test split, recent performance concentrated in a handful
    of semiconductor/AI-memory names).
  </footer>
</div>
<script>
const EQUITY = __EQUITY_JSON__;
(function () {
  const svg = document.getElementById("chart");
  const tip = document.getElementById("chart-tooltip");
  const W = 1040, H = 300, PAD_L = 50, PAD_R = 10, PAD_T = 14, PAD_B = 26;
  const xs = EQUITY.map(d => d.t);
  const ys = EQUITY.map(d => d.v);

  function niceTicks(dataMin, dataMax, targetCount) {
    const rough = (dataMax - dataMin) / targetCount || 1;
    const mag = Math.pow(10, Math.floor(Math.log10(rough)));
    const norm = rough / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const niceMin = Math.floor(dataMin / step) * step;
    const niceMax = Math.ceil(dataMax / step) * step;
    const ticks = [];
    for (let v = niceMin; v <= niceMax + step / 2; v += step) ticks.push(v);
    return ticks;
  }

  function quarterTicks(minT, maxT) {
    const start = new Date(minT);
    let d = new Date(start.getFullYear(), Math.floor(start.getMonth() / 3) * 3, 1);
    const ticks = [];
    while (d.getTime() <= maxT) {
      if (d.getTime() >= minT) ticks.push(d.getTime());
      d = new Date(d.getFullYear(), d.getMonth() + 3, 1);
    }
    return ticks;
  }

  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const yTicks = niceTicks(Math.min(...ys), Math.max(...ys), 5);
  const minY = yTicks[0], maxY = yTicks[yTicks.length - 1];
  const xScale = t => PAD_L + (t - minX) / (maxX - minX) * (W - PAD_L - PAD_R);
  const yScale = v => H - PAD_B - (v - minY) / (maxY - minY) * (H - PAD_T - PAD_B);

  let path = "";
  EQUITY.forEach((d, i) => { path += (i === 0 ? "M" : "L") + xScale(d.t).toFixed(1) + "," + yScale(d.v).toFixed(1) + " "; });

  let gridSvg = "";
  yTicks.forEach(v => {
    const y = yScale(v);
    gridSvg += `<line x1="${PAD_L}" x2="${W - PAD_R}" y1="${y}" y2="${y}" stroke="var(--border)" stroke-width="1"/>`;
    gridSvg += `<text x="4" y="${y + 3}">${v.toFixed(0)}</text>`;
  });
  quarterTicks(minX, maxX).forEach(t => {
    const x = xScale(t);
    const label = new Date(t).toLocaleString("en-US", { month: "short", year: "2-digit" });
    gridSvg += `<text x="${x}" y="${H - 6}" text-anchor="middle">${label}</text>`;
  });

  svg.innerHTML = gridSvg +
    `<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/>` +
    `<circle id="hover-dot" r="4" fill="var(--accent)" style="display:none"/>`;

  const dot = document.getElementById("hover-dot");
  svg.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / rect.width * W;
    let best = 0, bestDist = Infinity;
    EQUITY.forEach((d, i) => {
      const dist = Math.abs(xScale(d.t) - mx);
      if (dist < bestDist) { bestDist = dist; best = i; }
    });
    const d = EQUITY[best];
    dot.setAttribute("cx", xScale(d.t));
    dot.setAttribute("cy", yScale(d.v));
    dot.style.display = "block";
    tip.style.display = "block";
    tip.style.left = (e.clientX - rect.left + 12) + "px";
    tip.style.top = (e.clientY - rect.top - 10) + "px";
    tip.textContent = d.date + "  $" + d.v.toFixed(2);
  });
  svg.addEventListener("mouseleave", () => { dot.style.display = "none"; tip.style.display = "none"; });
})();
</script>
</body>
</html>
"""

ACTIVITY_ROW = """<div class="activity-row"><span class="activity-date">{date}</span><span>{text}</span></div>"""
TABLE_ROW = """<tr><td>{period}</td><td>{entry_date}</td><td class="tickers">{holdings}</td><td class="num">{value}</td></tr>"""


def _diff_text(old: set, new: set) -> str:
    sold = sorted(old - new)
    bought = sorted(new - old)
    kept = sorted(old & new)
    parts = []
    if bought:
        parts.append('bought ' + ' '.join(f'<span class="chip bought">{t}</span>' for t in bought))
    if sold:
        parts.append('sold ' + ' '.join(f'<span class="chip sold">{t}</span>' for t in sold))
    if kept:
        parts.append('kept ' + ' '.join(f'<span class="chip">{t}</span>' for t in kept))
    return '; '.join(parts) if parts else 'no change'


def build():
    equity = pd.read_csv(EQUITY_CSV, parse_dates=["date"]).sort_values("date")
    rebal = pd.read_csv(REBALANCE_CSV)

    equity_points = [{"t": int(row.date.timestamp() * 1000), "v": round(float(row.value), 2),
                       "date": row.date.date().isoformat()} for row in equity.itertuples()]

    activity_rows = []
    for i in range(len(rebal) - 1, max(len(rebal) - 3, 0), -1):
        new_set = set(rebal.iloc[i]["holdings"].split(","))
        old_set = set(rebal.iloc[i - 1]["holdings"].split(",")) if i > 0 else set()
        text = _diff_text(old_set, new_set)
        activity_rows.append(ACTIVITY_ROW.format(date=rebal.iloc[i]["entry_date"], text=text))
    activity_html = "\n".join(activity_rows) if activity_rows else "<p>No rebalances recorded yet.</p>"

    value_by_date = equity.set_index("date")["value"]
    table_rows = []
    for _, row in rebal.iloc[::-1].iterrows():
        entry_ts = pd.Timestamp(row["entry_date"])
        value = value_by_date.loc[entry_ts] if entry_ts in value_by_date.index else None
        value_str = f"{value:,.2f}" if value is not None else "-"
        table_rows.append(TABLE_ROW.format(
            period=row["period"], entry_date=row["entry_date"],
            holdings=row["holdings"].replace(",", ", "), value=value_str))

    as_of = equity["date"].max().date().isoformat()

    html = (PAGE_TEMPLATE
            .replace("__AS_OF__", as_of)
            .replace("__ACTIVITY_HTML__", activity_html)
            .replace("__TABLE_ROWS__", "\n".join(table_rows))
            .replace("__EQUITY_JSON__", json.dumps(equity_points)))
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_HTML} ({len(equity_points)} equity points, {len(rebal)} rebalance rows)")


if __name__ == "__main__":
    build()
