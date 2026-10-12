"""
Current S&P 500 constituent list, scraped from Wikipedia (cached 7 days),
same pattern as method1-tracker's stock_universe.py. No point-in-time
correction needed here (unlike the method2 backtest) - this tracker only
ever asks "what's eligible RIGHT NOW" for a live, present-tense decision,
which carries no survivorship bias.
"""

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_CACHE_FILE = Path(__file__).with_name("sp500_constituents.json")
SP500_CACHE_MAX_AGE_DAYS = 7


def _utcnow():
    return datetime.now(timezone.utc)


def get_sp500_tickers(force_refresh: bool = False) -> list[str]:
    if not force_refresh and SP500_CACHE_FILE.exists():
        try:
            cached = json.loads(SP500_CACHE_FILE.read_text())
            cached_at = datetime.fromisoformat(cached["cached_at"])
            if _utcnow() - cached_at < timedelta(days=SP500_CACHE_MAX_AGE_DAYS):
                return cached["tickers"]
        except Exception:
            pass

    resp = None
    try:
        import requests
        # Wikipedia 403s unidentified clients - pd.read_html's own request
        # doesn't set a User-Agent, so fetch with requests first.
        resp = requests.get(SP500_WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        symbols = tables[0]["Symbol"].tolist()
        tickers = [str(s).strip().replace(".", "-") for s in symbols if str(s).strip()]
    except Exception as e:
        if SP500_CACHE_FILE.exists():
            print(f"  Could not refresh S&P 500 list from Wikipedia ({e}); reusing stale cache.")
            return json.loads(SP500_CACHE_FILE.read_text())["tickers"]
        raise

    SP500_CACHE_FILE.write_text(json.dumps(
        {"cached_at": _utcnow().isoformat(), "tickers": tickers}, indent=2))
    return tickers
