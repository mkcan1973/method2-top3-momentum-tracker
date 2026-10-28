"""
Builds the single static index.html dashboard - inline JSON + hand-rolled
SVG chart, no client-side fetch and no charting library, same
no-dependency approach method1-tracker's web_summary.py uses.
"""

import json
from pathlib import Path

import pandas as pd

import fetch

OUT_DIR = Path(__file__).parent
EQUITY_CSV = OUT_DIR / "equity_history.csv"
REBALANCE_CSV = OUT_DIR / "rebalance_log.csv"
SLEEVE_A_CSV = OUT_DIR / "sleeve_a_log.csv"
SPY_CSV = OUT_DIR / "spy_history.csv"
OUT_HTML = OUT_DIR / "index.html"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blended Momentum Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg-page: #f6f7f9; --bg-panel: #ffffff; --ink-1: #16181d; --ink-2: #555b66;
  --border: #e3e5e9; --accent: #2a66f0; --up: #1a8a4a; --down: #d1402f; --bench: #c07a1e;
  --chip-bg: #eef2fd;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg-page: #14161a; --bg-panel: #1c1f26; --ink-1: #eef0f3; --ink-2: #a3a9b3;
    --border: #2d313a; --accent: #6f9bff; --up: #38c172; --down: #ff6b5e; --bench: #e0a940;
    --chip-bg: #202845;
  }
}
:root[data-theme="dark"] {
  --bg-page: #14161a; --bg-panel: #1c1f26; --ink-1: #eef0f3; --ink-2: #a3a9b3;
  --border: #2d313a; --accent: #6f9bff; --up: #38c172; --down: #ff6b5e; --bench: #e0a940;
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
#chart-tooltip, .tooltip-box {
  position: absolute; display: none; background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 8px; font-size: 0.8rem; font-family: "IBM Plex Mono", monospace;
  pointer-events: none; color: var(--ink-1);
}
footer { color: var(--ink-2); font-size: 0.78rem; margin-top: 24px; line-height: 1.5; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Blended Momentum Tracker</h1>
  <p class="sub">As of __AS_OF__ &middot; 50% sleeve A (one stock, picked every January by prior-year return, 35% stop-loss) + 50% sleeve B (top-3, 6-month momentum, rebalanced monthly) &middot; rebalanced to 50/50 every January</p>

  <div class="panel">
    <h2>Current holdings</h2>
    __CURRENT_HOLDINGS_HTML__
  </div>

  <div class="panel">
    <h2>Recent activity</h2>
    __ACTIVITY_HTML__
  </div>

  <div class="panel">
    <div style="display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:8px;">
      <h2 style="margin:0;">Equity curve</h2>
      <label style="font-size:0.85rem; color:var(--ink-2);">Rebase $200 at start of
        <select id="start-year" style="font-family:'IBM Plex Mono',monospace; font-size:0.85rem; padding:2px 4px;">
          __YEAR_OPTIONS__
        </select>
      </label>
    </div>
    <div style="font-size:0.8rem; color:var(--ink-2); margin-top:4px;">
      <span style="color:var(--accent);">&#9644;</span> strategy &nbsp;
      <span style="color:var(--bench);">&#9644;</span> S&amp;P 500 (SPY)
    </div>
    <div style="position:relative; margin-top:4px;">
      <svg id="chart" viewBox="0 0 1040 300" width="100%" style="overflow:visible;"></svg>
      <div style="position:absolute; top:4px; right:6px; text-align:right; font-family:'IBM Plex Mono',monospace;">
        <div id="cagr-label" style="font-size:0.85rem; font-weight:600; color:var(--accent);"></div>
        <div id="spy-cagr-label" style="font-size:0.85rem; font-weight:600; color:var(--bench);"></div>
      </div>
      <div id="chart-tooltip"></div>
    </div>
  </div>

  <div class="panel">
    <h2 style="margin:0 0 4px;">Annual returns</h2>
    <p class="sub" style="margin:0 0 8px;">Bars: each calendar year's own return. Line: cumulative CAGR from the selected start year through the end of that year. Current year is partial (YTD).</p>
    <div style="position:relative;">
      <svg id="returns-chart" viewBox="0 0 1040 260" width="100%" style="overflow:visible;"></svg>
      <div id="returns-spy-cagr-label" style="position:absolute; top:4px; right:6px; font-size:0.85rem; font-weight:600; color:var(--bench); font-family:'IBM Plex Mono',monospace;"></div>
      <div id="returns-tooltip" class="tooltip-box"></div>
    </div>
  </div>

  <div class="panel">
    <h2>Sleeve A: yearly pick history</h2>
    <table>
      <thead><tr><th>Year</th><th>Ticker</th><th>Entry date</th><th>Status</th><th class="num">Value ($200 base)</th></tr></thead>
      <tbody id="sleeve-a-body">__SLEEVE_A_ROWS__</tbody>
    </table>
  </div>

  <div class="panel">
    <h2>Sleeve B: monthly top-3 holdings</h2>
    <table>
      <thead><tr><th>Month</th><th>Rebalance date</th><th class="tickers">Holdings</th><th class="num">Value ($200 base)</th></tr></thead>
      <tbody id="holdings-body">__TABLE_ROWS__</tbody>
    </table>
  </div>

  <footer>
    Research/educational tracker only - not auto-traded, not investment advice. This blend (50% sleeve A /
    50% sleeve B, rebalanced every January) was chosen from method2's method_combination_analysis.py as the
    2-method pair with the most consistent year-by-year returns (13/13 up-years, 2013-2025, point-in-time
    corrected S&amp;P 500 membership). Holdings through the method2 backtest's last completed period come from
    that historical backtest (C:\\mark\\scripts\\method2); everything after that is computed live against the
    S&amp;P 500's actual current constituent list. No transaction costs or taxes modeled. Sleeve A is a
    concentrated, small-sample, single-stock strategy - its strong backtested record reflects the specific
    historical picks it happened to land on, not a robustly validated edge. No train/test split has been done.
  </footer>
</div>
<script>
const EQUITY_RAW = __EQUITY_JSON__;
const SPY_RAW = __SPY_JSON__;
const DEFAULT_START_YEAR = __DEFAULT_START_YEAR__;
// Displayed as $100/sleeve x 2 sleeves = $200 total, matching how each sleeve's OWN
// standalone backtest is independently normalized to $100 (see method2/best_combo_equity.png) -
// not a change to the underlying data, which stays in its own internally consistent unit.
const DISPLAY_BASE = 200;
(function () {
  const svg = document.getElementById("chart");
  const tip = document.getElementById("chart-tooltip");
  const cagrLabel = document.getElementById("cagr-label");
  const spyCagrLabel = document.getElementById("spy-cagr-label");
  const yearSelect = document.getElementById("start-year");
  const W = 1040, H = 300, PAD_L = 50, PAD_R = 10, PAD_T = 14, PAD_B = 26;

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

  function yearTicks(minT, maxT) {
    const ticks = [];
    for (let y = new Date(minT).getFullYear(); y <= new Date(maxT).getFullYear(); y++) {
      const t = new Date(y, 0, 1).getTime();
      if (t >= minT && t <= maxT) ticks.push(t);
    }
    return ticks;
  }

  function rebaseSeries(raw, startYear) {
    const cutoff = new Date(startYear, 0, 1).getTime();
    const point = raw.find(d => d.t >= cutoff) || raw[0];
    const factor = DISPLAY_BASE / point.v;
    return raw.filter(d => d.t >= cutoff).map(d => ({ t: d.t, v: d.v * factor, date: d.date }));
  }

  function seriesCagr(data) {
    const years = (data[data.length - 1].t - data[0].t) / (1000 * 60 * 60 * 24 * 365.25);
    return years > 0 ? Math.pow(data[data.length - 1].v / data[0].v, 1 / years) - 1 : 0;
  }

  function render(startYear) {
    const data = rebaseSeries(EQUITY_RAW, startYear);
    const spyData = rebaseSeries(SPY_RAW, startYear);
    const xs = data.map(d => d.t), ys = data.map(d => d.v).concat(spyData.map(d => d.v));

    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const yTicks = niceTicks(Math.min(...ys), Math.max(...ys), 5);
    const minY = yTicks[0], maxY = yTicks[yTicks.length - 1];
    const xScale = t => PAD_L + (t - minX) / (maxX - minX) * (W - PAD_L - PAD_R);
    const yScale = v => H - PAD_B - (v - minY) / (maxY - minY) * (H - PAD_T - PAD_B);

    let path = "";
    data.forEach((d, i) => { path += (i === 0 ? "M" : "L") + xScale(d.t).toFixed(1) + "," + yScale(d.v).toFixed(1) + " "; });
    let spyPath = "";
    spyData.forEach((d, i) => { spyPath += (i === 0 ? "M" : "L") + xScale(d.t).toFixed(1) + "," + yScale(d.v).toFixed(1) + " "; });

    let gridSvg = "";
    yTicks.forEach(v => {
      const y = yScale(v);
      gridSvg += `<line x1="${PAD_L}" x2="${W - PAD_R}" y1="${y}" y2="${y}" stroke="var(--border)" stroke-width="1"/>`;
      gridSvg += `<text x="4" y="${y + 3}">${v.toFixed(0)}</text>`;
    });
    const spanYears = (maxX - minX) / (1000 * 60 * 60 * 24 * 365.25);
    const useYearly = spanYears > 3;
    (useYearly ? yearTicks(minX, maxX) : quarterTicks(minX, maxX)).forEach(t => {
      const x = xScale(t);
      const label = useYearly
        ? String(new Date(t).getFullYear())
        : new Date(t).toLocaleString("en-US", { month: "short", year: "2-digit" });
      gridSvg += `<text x="${x}" y="${H - 6}" text-anchor="middle">${label}</text>`;
    });

    svg.innerHTML = gridSvg +
      `<path d="${spyPath}" fill="none" stroke="var(--bench)" stroke-width="2"/>` +
      `<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/>` +
      `<circle id="hover-dot" r="4" fill="var(--accent)" style="display:none"/>` +
      `<circle id="hover-dot-spy" r="4" fill="var(--bench)" style="display:none"/>`;

    const dot = document.getElementById("hover-dot");
    const dotSpy = document.getElementById("hover-dot-spy");
    svg.onmousemove = (e) => {
      const rect = svg.getBoundingClientRect();
      const mx = (e.clientX - rect.left) / rect.width * W;
      let best = 0, bestDist = Infinity;
      data.forEach((d, i) => {
        const dist = Math.abs(xScale(d.t) - mx);
        if (dist < bestDist) { bestDist = dist; best = i; }
      });
      const d = data[best];
      const dSpy = spyData[Math.min(best, spyData.length - 1)];
      dot.setAttribute("cx", xScale(d.t));
      dot.setAttribute("cy", yScale(d.v));
      dot.style.display = "block";
      dotSpy.setAttribute("cx", xScale(dSpy.t));
      dotSpy.setAttribute("cy", yScale(dSpy.v));
      dotSpy.style.display = "block";
      tip.style.display = "block";
      tip.style.left = (e.clientX - rect.left + 12) + "px";
      tip.style.top = (e.clientY - rect.top - 10) + "px";
      tip.innerHTML = `${d.date}<br>strategy: $${d.v.toFixed(2)}<br>S&amp;P 500: $${dSpy.v.toFixed(2)}`;
    };
    svg.onmouseleave = () => { dot.style.display = "none"; dotSpy.style.display = "none"; tip.style.display = "none"; };

    cagrLabel.textContent = `Strategy CAGR since ${startYear}-01-01: ${(seriesCagr(data) * 100).toFixed(1)}%`;
    spyCagrLabel.textContent = `S&P 500 CAGR since ${startYear}-01-01: ${(seriesCagr(spyData) * 100).toFixed(1)}%`;

    const tableFactor = DISPLAY_BASE / (EQUITY_RAW.find(d => d.t >= minX) || EQUITY_RAW[0]).v;
    document.querySelectorAll("#holdings-body tr, #sleeve-a-body tr").forEach(tr => {
      const rowYear = parseInt(tr.dataset.year, 10);
      if (rowYear < startYear) { tr.style.display = "none"; return; }
      tr.style.display = "";
      const cell = tr.querySelector("td.num");
      const raw = parseFloat(cell.dataset.value);
      cell.textContent = (raw * tableFactor).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    });

    ["sleeve-a-value", "sleeve-b-value"].forEach(id => {
      const el = document.getElementById(id);
      const raw = parseFloat(el.dataset.rawValue);
      el.textContent = "$" + (raw * tableFactor).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    });
  }

  function renderReturns(startYear) {
    const svg2 = document.getElementById("returns-chart");
    const tip2 = document.getElementById("returns-tooltip");
    const W2 = 1040, H2 = 260, PAD_L2 = 50, PAD_R2 = 46, PAD_T2 = 14, PAD_B2 = 24;
    const todayYear = new Date().getFullYear();
    const maxYear = new Date(EQUITY_RAW[EQUITY_RAW.length - 1].t).getFullYear();
    const startPoint = EQUITY_RAW.find(d => new Date(d.t).getFullYear() >= startYear) || EQUITY_RAW[0];

    const spyStart = SPY_RAW.find(d => new Date(d.t).getFullYear() >= startYear) || SPY_RAW[0];
    const spyEnd = SPY_RAW[SPY_RAW.length - 1];
    const spyYearsElapsed = (spyEnd.t - spyStart.t) / (1000 * 60 * 60 * 24 * 365.25);
    const spyCagrToNow = spyYearsElapsed > 0 ? Math.pow(spyEnd.v / spyStart.v, 1 / spyYearsElapsed) - 1 : 0;
    document.getElementById("returns-spy-cagr-label").textContent =
      `S&P 500 CAGR since ${startYear}: ${(spyCagrToNow * 100).toFixed(1)}%`;

    const bars = [];
    for (let y = startYear; y <= maxYear; y++) {
      const pts = EQUITY_RAW.filter(d => new Date(d.t).getFullYear() === y);
      if (pts.length < 2) continue;
      const last = pts[pts.length - 1];
      const yearsElapsed = (last.t - startPoint.t) / (1000 * 60 * 60 * 24 * 365.25);
      const cumCagr = yearsElapsed > 0 ? Math.pow(last.v / startPoint.v, 1 / yearsElapsed) - 1 : 0;
      bars.push({ year: y, ret: last.v / pts[0].v - 1, cumCagr, partial: y === todayYear });
    }
    if (bars.length === 0) { svg2.innerHTML = ""; return; }

    const rets = bars.map(b => b.ret * 100);
    const cagrs = bars.map(b => b.cumCagr * 100);
    const yTicksL = niceTicks(Math.min(0, ...rets), Math.max(0, ...rets), 5);
    const minYL = yTicksL[0], maxYL = yTicksL[yTicksL.length - 1];
    const yScaleL = v => H2 - PAD_B2 - (v - minYL) / (maxYL - minYL) * (H2 - PAD_T2 - PAD_B2);

    const yTicksR = niceTicks(Math.min(0, ...cagrs), Math.max(0, ...cagrs), 5);
    const minYR = yTicksR[0], maxYR = yTicksR[yTicksR.length - 1];
    const yScaleR = v => H2 - PAD_B2 - (v - minYR) / (maxYR - minYR) * (H2 - PAD_T2 - PAD_B2);

    const slot = (W2 - PAD_L2 - PAD_R2) / bars.length;
    const barW = slot * 0.55;
    const xCenter = i => PAD_L2 + i * slot + slot / 2;

    let gridSvg = "";
    yTicksL.forEach(v => {
      const y = yScaleL(v);
      gridSvg += `<line x1="${PAD_L2}" x2="${W2 - PAD_R2}" y1="${y}" y2="${y}" stroke="var(--border)" stroke-width="1"/>`;
      gridSvg += `<text x="4" y="${y + 3}">${v.toFixed(0)}%</text>`;
    });
    yTicksR.forEach(v => {
      const y = yScaleR(v);
      gridSvg += `<text x="${W2 - PAD_R2 + 6}" y="${y + 3}" fill="var(--accent)">${v.toFixed(0)}%</text>`;
    });

    let barsSvg = "";
    bars.forEach((b, i) => {
      const x = PAD_L2 + i * slot + (slot - barW) / 2;
      const yZero = yScaleL(0), yVal = yScaleL(b.ret * 100);
      const top = Math.min(yZero, yVal), height = Math.max(1, Math.abs(yZero - yVal));
      const color = b.ret >= 0 ? "var(--up)" : "var(--down)";
      const opacity = b.partial ? 0.55 : 1;
      barsSvg += `<rect data-i="${i}" x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${barW.toFixed(1)}" height="${height.toFixed(1)}" fill="${color}" opacity="${opacity}"/>`;
      const label = b.partial ? `${b.year} YTD` : String(b.year);
      barsSvg += `<text x="${(x + barW / 2).toFixed(1)}" y="${H2 - 6}" text-anchor="middle">${label}</text>`;
    });

    let cagrSvg = "";
    let linePath = "";
    bars.forEach((b, i) => {
      const px = xCenter(i), py = yScaleR(b.cumCagr * 100);
      linePath += (i === 0 ? "M" : "L") + px.toFixed(1) + "," + py.toFixed(1) + " ";
      cagrSvg += `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3" fill="var(--accent)"/>`;
    });
    cagrSvg = `<path d="${linePath}" fill="none" stroke="var(--accent)" stroke-width="2"/>` + cagrSvg;

    const legendSvg =
      `<rect x="${W2 - 270}" y="0" width="10" height="10" fill="var(--up)"/>` +
      `<text x="${W2 - 255}" y="9">Year's own return (left axis)</text>` +
      `<line x1="${W2 - 270}" x2="${W2 - 260}" y1="20" y2="20" stroke="var(--accent)" stroke-width="2"/>` +
      `<text x="${W2 - 255}" y="23" fill="var(--accent)">CAGR since ${startYear} (right axis)</text>`;

    svg2.innerHTML = gridSvg + barsSvg + cagrSvg + legendSvg;
    svg2.onmousemove = (e) => {
      const rect = svg2.getBoundingClientRect();
      const mx = (e.clientX - rect.left) / rect.width * W2;
      const i = Math.min(bars.length - 1, Math.max(0, Math.floor((mx - PAD_L2) / slot)));
      const b = bars[i];
      if (!b) { tip2.style.display = "none"; return; }
      tip2.style.display = "block";
      tip2.style.left = (e.clientX - rect.left + 12) + "px";
      tip2.style.top = (e.clientY - rect.top - 10) + "px";
      const yearLabel = b.partial ? `${b.year} YTD` : String(b.year);
      tip2.innerHTML = `${yearLabel}<br>return: ${(b.ret * 100).toFixed(1)}%<br>CAGR since ${startYear}: ${(b.cumCagr * 100).toFixed(1)}%`;
    };
    svg2.onmouseleave = () => { tip2.style.display = "none"; };
  }

  function renderAll(startYear) {
    render(startYear);
    renderReturns(startYear);
  }

  yearSelect.value = String(DEFAULT_START_YEAR);
  yearSelect.addEventListener("change", () => renderAll(parseInt(yearSelect.value, 10)));
  renderAll(DEFAULT_START_YEAR);
})();
</script>
</body>
</html>
"""

ACTIVITY_ROW = """<div class="activity-row"><span class="activity-date">{date}</span><span>{text}</span></div>"""
TABLE_ROW = ('<tr data-year="{year}"><td>{period}</td><td>{entry_date}</td>'
             '<td class="tickers">{holdings}</td><td class="num" data-value="{raw_value}">{value}</td></tr>')
SLEEVE_A_ROW = ('<tr data-year="{year}"><td>{year}</td><td class="tickers">{ticker}</td><td>{entry_date}</td>'
                 '<td>{status}</td><td class="num" data-value="{raw_value}">{value}</td></tr>')
DEFAULT_START_YEAR = 2025
DISPLAY_BASE = 200  # keep in sync with the JS DISPLAY_BASE constant in PAGE_TEMPLATE


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
    sleeve_a = pd.read_csv(SLEEVE_A_CSV)
    spy = pd.read_csv(SPY_CSV, parse_dates=["date"]).sort_values("date")

    equity_points = [{"t": int(row.date.timestamp() * 1000), "v": round(float(row.value), 2),
                       "date": row.date.date().isoformat()} for row in equity.itertuples()]
    spy_points = [{"t": int(row.date.timestamp() * 1000), "v": round(float(row.value), 2),
                    "date": row.date.date().isoformat()} for row in spy.itertuples()]

    value_by_date = equity.set_index("date")["value"]

    # --- Current holdings box: entry/current price + % change per ticker ---
    cur_a = sleeve_a.iloc[-1]
    cur_b = rebal.iloc[-1]
    a_stopped = bool(cur_a["stopped_out"])
    b_tickers = cur_b["holdings"].split(",")
    b_entry_prices = dict(zip(b_tickers, (float(p) for p in cur_b["entry_prices"].split(","))))

    live_tickers = b_tickers + ([] if a_stopped else [cur_a["ticker"]])
    live_prices = {}
    try:
        fetched = fetch.fetch_prices(live_tickers, start=(pd.Timestamp.today() - pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
        for t, df in fetched.items():
            if not df.empty:
                live_prices[t] = float(df["close"].iloc[-1])
    except Exception as e:
        print(f"  WARNING: live price fetch for current-holdings box failed ({e}); showing entry prices only.")

    def _price_line(ticker: str, entry_price: float, current_price: float | None, note: str = "") -> str:
        if current_price is None:
            return f'<span class="chip">{ticker}</span> entry ${entry_price:,.2f}{note}'
        pct = (current_price / entry_price - 1) * 100
        cls = "up" if pct >= 0 else "down"
        return (f'<span class="chip">{ticker}</span> entry ${entry_price:,.2f} &rarr; '
                f'current ${current_price:,.2f} <span style="color:var(--{cls});">({pct:+.1f}%)</span>{note}')

    if a_stopped:
        a_html = _price_line(cur_a["ticker"], float(cur_a["entry_price"]), float(cur_a["exit_price"]),
                              note=f' — stopped out {cur_a["exit_date"]}, in cash until next January')
    else:
        a_html = _price_line(cur_a["ticker"], float(cur_a["entry_price"]), live_prices.get(cur_a["ticker"]),
                              note=f' (since {cur_a["entry_date"]})')

    b_html = "<br>".join(
        _price_line(t, b_entry_prices[t], live_prices.get(t)) for t in b_tickers)

    # Sleeve values in the SAME raw unit as EQUITY_RAW (not yet rebased to any display year) -
    # JS rescales these to match the chart's selected start-year on load and on dropdown change,
    # same as it already does for the holdings tables.
    a_entry_price = float(cur_a["entry_price"])
    a_cur_price = float(cur_a["exit_price"]) if a_stopped else live_prices.get(cur_a["ticker"], a_entry_price)
    sleeve_a_value_raw = float(cur_a["basis_value"]) * (a_cur_price / a_entry_price)

    basis_per_slot = float(cur_b["basis_value_per_slot"])
    sleeve_b_value_raw = sum(
        basis_per_slot * (live_prices.get(t, b_entry_prices[t]) / b_entry_prices[t]) for t in b_tickers
    )

    current_holdings_html = (
        f'<div class="activity-row"><span>Sleeve A (50%): <strong id="sleeve-a-value" '
        f'data-raw-value="{sleeve_a_value_raw}">${sleeve_a_value_raw:,.2f}</strong></span>'
        f'<span>{a_html}</span></div>'
        f'<div class="activity-row"><span>Sleeve B (50%): <strong id="sleeve-b-value" '
        f'data-raw-value="{sleeve_b_value_raw}">${sleeve_b_value_raw:,.2f}</strong></span>'
        f'<span>{b_html}</span></div>'
    )

    # --- Recent activity: sleeve A's current status + sleeve B's last 2 monthly diffs ---
    a_status = (f'stopped out {cur_a["exit_date"]} @ {float(cur_a["exit_price"]):.2f} — in cash until next January'
                if a_stopped else f'holding since {cur_a["entry_date"]}')
    activity_rows = [ACTIVITY_ROW.format(
        date=cur_a["entry_date"] if not a_stopped else cur_a["exit_date"],
        text=f'Sleeve A: {cur_a["ticker"]} {a_status}')]
    for i in range(len(rebal) - 1, max(len(rebal) - 3, 0), -1):
        new_set = set(rebal.iloc[i]["holdings"].split(","))
        old_set = set(rebal.iloc[i - 1]["holdings"].split(",")) if i > 0 else set()
        text = _diff_text(old_set, new_set)
        activity_rows.append(ACTIVITY_ROW.format(date=rebal.iloc[i]["entry_date"], text=f"Sleeve B: {text}"))
    activity_html = "\n".join(activity_rows)

    table_rows = []
    for _, row in rebal.iloc[::-1].iterrows():
        entry_ts = pd.Timestamp(row["entry_date"])
        value = value_by_date.loc[entry_ts] if entry_ts in value_by_date.index else None
        value_str = f"{value:,.2f}" if value is not None else "-"
        table_rows.append(TABLE_ROW.format(
            year=int(row["period"][:4]), period=row["period"], entry_date=row["entry_date"],
            holdings=row["holdings"].replace(",", ", "), value=value_str,
            raw_value=value if value is not None else 0))

    sleeve_a_rows = []
    for idx, row in sleeve_a.iloc[::-1].iterrows():
        entry_ts = pd.Timestamp(row["entry_date"])
        value = value_by_date.loc[entry_ts] if entry_ts in value_by_date.index else None
        value_str = f"{value:,.2f}" if value is not None else "-"
        is_current = idx == sleeve_a.index[-1]
        if bool(row["stopped_out"]):
            status = f'stopped out {row["exit_date"]}'
        elif is_current:
            status = "holding (current)"
        else:
            status = "held full year"
        sleeve_a_rows.append(SLEEVE_A_ROW.format(
            year=int(row["year"]), ticker=row["ticker"], entry_date=row["entry_date"],
            status=status, value=value_str, raw_value=value if value is not None else 0))

    as_of = equity["date"].max().date().isoformat()
    min_year = equity["date"].min().year
    max_year = equity["date"].max().year
    year_options = "\n".join(
        f'<option value="{y}"{" selected" if y == DEFAULT_START_YEAR else ""}>{y}</option>'
        for y in range(min_year, max_year + 1))

    html = (PAGE_TEMPLATE
            .replace("__AS_OF__", as_of)
            .replace("__CURRENT_HOLDINGS_HTML__", current_holdings_html)
            .replace("__ACTIVITY_HTML__", activity_html)
            .replace("__TABLE_ROWS__", "\n".join(table_rows))
            .replace("__SLEEVE_A_ROWS__", "\n".join(sleeve_a_rows))
            .replace("__EQUITY_JSON__", json.dumps(equity_points))
            .replace("__SPY_JSON__", json.dumps(spy_points))
            .replace("__YEAR_OPTIONS__", year_options)
            .replace("__DEFAULT_START_YEAR__", str(DEFAULT_START_YEAR)))
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_HTML} ({len(equity_points)} equity points, {len(rebal)} sleeve B rows, {len(sleeve_a)} sleeve A rows)")


if __name__ == "__main__":
    build()
