#!/usr/bin/env python3
"""
Taiwan Market Dashboard - Data Fetcher
Fetches VIX data, CNN Fear & Greed, and Taiwan institutional investor data.
Outputs to data/market_data.json for the static GitHub Pages site.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import urllib3
import requests
import yfinance as yf

TW_TZ = timezone(timedelta(hours=8))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "market_data.json")

# Set NO_SSL_VERIFY=1 to skip SSL verification (useful on corporate/local machines)
SSL_VERIFY = os.environ.get("NO_SSL_VERIFY", "0") != "1"
if not SSL_VERIFY:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("SSL verification disabled (NO_SSL_VERIFY=1)", file=sys.stderr)

# Shared requests session
_session = requests.Session()
_session.verify = SSL_VERIFY
_session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; MarketDashboard/1.0)"})


def fetch_vixtwn_from_taifex():
    """
    Fetch Taiwan VIX (VIXTWN) from TAIFEX MIS.
    Strategy 1: REST API POST /futures/api/getQuoteListVIX (fast, no browser)
    Strategy 2: Direct SockJS WebSocket
    Strategy 3: Playwright browser (slowest fallback)
    """
    # Strategy 1: REST API (simplest and fastest)
    result = _vixtwn_rest_api()
    if result:
        print(f"VIXTWN via REST API: {result['current']}", file=sys.stderr)
        return result

    import asyncio
    try:
        result = asyncio.run(_vixtwn_direct_ws())
        if result:
            print(f"VIXTWN via direct WebSocket: {result['current']}", file=sys.stderr)
            return result
    except Exception as e:
        print(f"Warning: VIXTWN direct WS failed: {e}", file=sys.stderr)
    try:
        result = asyncio.run(_vixtwn_playwright())
        if result:
            print(f"VIXTWN via Playwright: {result['current']}", file=sys.stderr)
            return result
    except Exception as e:
        print(f"Warning: VIXTWN Playwright failed: {e}", file=sys.stderr)
    return None


def _vixtwn_rest_api():
    """Fetch VIXTWN from TAIFEX REST API (POST getQuoteListVIX)."""
    try:
        resp = _session.post(
            "https://mis.taifex.com.tw/futures/api/getQuoteListVIX",
            json={},
            headers={"Referer": "https://mis.taifex.com.tw/futures/VolatilityQuotes/"},
            timeout=12,
        )
        data = resp.json()
        if data.get("RtCode") != "0":
            return None
        quote_list = data.get("RtData", {}).get("QuoteList", [])
        if not quote_list:
            return None
        q = quote_list[0]
        current = float(q.get("CLastPrice") or 0)
        if current <= 0:
            return None
        prev = float(q.get("CRefPrice") or 0)
        open_ = float(q.get("COpenPrice") or 0)
        high  = float(q.get("CHighPrice") or 0)
        low   = float(q.get("CLowPrice") or 0)
        return {
            "symbol":     "VIXTWN",
            "current":    round(current, 2),
            "prev":       round(prev, 2) if prev else None,
            "change":     round(current - prev, 2) if prev else None,
            "change_pct": round((current - prev) / prev * 100, 2) if prev else None,
            "open":       round(open_, 2) if open_ else None,
            "high":       round(high, 2) if high else None,
            "low":        round(low, 2) if low else None,
            "high_52w":   None,
            "low_52w":    None,
        }
    except Exception as e:
        print(f"Warning: VIXTWN REST API failed: {e}", file=sys.stderr)
        return None


def _vixtwn_parse_values(vals):
    """Parse TAIFEX TAIWANVIX field dict into a structured result."""
    current  = float(vals.get("125", 0) or 0)
    if current <= 0:
        return None
    prev_cls = float(vals.get("129", 0) or 0)
    return {
        "symbol": "VIXTWN",
        "current": round(current, 2),
        "prev": round(prev_cls, 2) if prev_cls else None,
        "change": round(current - prev_cls, 2) if prev_cls else None,
        "change_pct": round((current - prev_cls) / prev_cls * 100, 2) if prev_cls else None,
        "open":  round(float(vals.get("126", 0) or 0), 2),
        "high":  round(float(vals.get("130", 0) or 0), 2),
        "low":   round(float(vals.get("131", 0) or 0), 2),
        "high_52w": None,
        "low_52w":  None,
    }


def _vixtwn_parse_sockjs(msg):
    """Parse a SockJS 'a' frame to extract TAIWANVIX quote data."""
    import re, json as _j
    m = re.match(r'^a(\[.*\])$', msg, re.DOTALL)
    if not m:
        return None
    try:
        arr = _j.loads(m.group(1))
        for item in arr:
            payload = _j.loads(item)
            if payload.get("type") == "quote":
                q = payload.get("quote", {})
                if q.get("symbol") == "TAIWANVIX":
                    return _vixtwn_parse_values(q.get("values", {}))
    except Exception:
        pass
    return None


async def _vixtwn_direct_ws():
    """Connect directly to TAIFEX SockJS WebSocket without a browser."""
    import asyncio, ssl, random, string, json as _j
    try:
        import websockets
    except ImportError:
        return None

    server = f"{random.randint(0, 999):03d}"
    sid    = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    url    = f"wss://mis.taifex.com.tw/futures/rt/{server}/{sid}/websocket"

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode    = ssl.CERT_NONE

    headers = {
        "Origin":  "https://mis.taifex.com.tw",
        "User-Agent": "Mozilla/5.0 (compatible; MarketDashboard/1.0)",
        "Referer": "https://mis.taifex.com.tw/futures/VolatilityQuotes/",
    }

    # websockets v14+ API
    connect_fn = getattr(websockets, "connect", None)
    if connect_fn is None:
        from websockets.asyncio.client import connect as connect_fn  # v14+

    extra_kw = {}
    import inspect
    sig = inspect.signature(connect_fn)
    param_names = set(sig.parameters)
    if "additional_headers" in param_names:
        extra_kw["additional_headers"] = headers
    elif "extra_headers" in param_names:
        extra_kw["extra_headers"] = headers

    try:
        async with connect_fn(url, ssl=ssl_ctx, open_timeout=10, ping_interval=None, **extra_kw) as ws:
            open_frame = await asyncio.wait_for(ws.recv(), timeout=5)
            if open_frame != "o":
                print(f"Warning: VIXTWN WS unexpected frame: {open_frame[:20]}", file=sys.stderr)
                return None
            sub = _j.dumps([_j.dumps({"type": "subscribe", "symbols": ["TAIWANVIX"]})])
            await ws.send(sub)
            for _ in range(20):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    if "TAIWANVIX" in msg:
                        result = _vixtwn_parse_sockjs(msg)
                        if result:
                            return result
                except asyncio.TimeoutError:
                    break
    except Exception as e:
        print(f"Warning: VIXTWN direct WS connect error: {e}", file=sys.stderr)
    return None


async def _vixtwn_playwright():
    """Playwright fallback: render TAIFEX page, click disclaimer, capture WS data."""
    from playwright.async_api import async_playwright
    import asyncio, re

    result_holder = {}
    ws_received = asyncio.Event()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--ignore-certificate-errors", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            locale="zh-TW",
        )
        page = await context.new_page()

        def on_ws(ws):
            print(f"Debug: VIXTWN WS connected {ws.url[:50]}", file=sys.stderr)
            def on_frame(payload):
                msg = str(payload)
                if "TAIWANVIX" in msg:
                    result = _vixtwn_parse_sockjs(msg)
                    if result:
                        result_holder["data"] = result
                        ws_received.set()
            ws.on("framereceived", on_frame)

        page.on("websocket", on_ws)

        await page.goto("https://mis.taifex.com.tw/futures/VolatilityQuotes/", timeout=30000)
        await page.wait_for_timeout(2000)

        # Click disclaimer: try text-based selectors first, then index
        clicked = False
        for sel in ['button:has-text("同意")', 'button:has-text("Agree")', 'button.btn-primary']:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    clicked = True
                    print(f"Debug: Clicked via selector {sel}", file=sys.stderr)
                    break
            except Exception:
                pass

        if not clicked:
            buttons = await page.query_selector_all("button")
            print(f"Debug: {len(buttons)} buttons found", file=sys.stderr)
            for i, btn in enumerate(buttons[:6]):
                try:
                    txt = (await btn.inner_text()).strip()[:20]
                    cls = (await btn.get_attribute("class") or "")[:30]
                    print(f"Debug:   btn[{i}] '{txt}' cls='{cls}'", file=sys.stderr)
                except Exception:
                    pass
            # Fall back to index 2 (worked locally)
            if len(buttons) >= 3:
                await buttons[2].scroll_into_view_if_needed()
                await buttons[2].click()
                print("Debug: Clicked btn[2]", file=sys.stderr)

        # Wait up to 35s for WebSocket data
        try:
            await asyncio.wait_for(ws_received.wait(), timeout=35)
        except asyncio.TimeoutError:
            print("Warning: VIXTWN Playwright WS timeout; trying DOM scrape", file=sys.stderr)
            # DOM scraping fallback: read current value from table cells
            try:
                cells = await page.query_selector_all("td")
                vals_found = []
                for cell in cells:
                    txt = (await cell.inner_text()).strip()
                    if re.match(r'^\d{2,3}\.\d{2}$', txt):
                        v = float(txt)
                        if 5 <= v <= 100:
                            vals_found.append(v)
                print(f"Debug: DOM values {vals_found}", file=sys.stderr)
                if vals_found:
                    result_holder["data"] = {
                        "symbol": "VIXTWN",
                        "current": vals_found[0],
                        "prev": None, "change": None, "change_pct": None,
                        "open": None, "high": None, "low": None,
                        "high_52w": None, "low_52w": None,
                    }
            except Exception as dom_err:
                print(f"Warning: VIXTWN DOM scrape error: {dom_err}", file=sys.stderr)

        await browser.close()

    return result_holder.get("data")


MA_STAT_KEYS = {"sp500", "nasdaq", "dji", "sox", "twii", "nikkei", "kospi"}
US_INDEX_KEYS = MA_STAT_KEYS  # kept for any reference elsewhere


def _compute_ma_stats(closes, current):
    """Compute MA20/60/240 and 60-day high, with % distance from current."""
    n = len(closes)
    stats = {}
    for days, key in [(20, "ma20"), (60, "ma60"), (240, "ma240")]:
        if n >= days:
            ma = round(float(closes.rolling(days).mean().iloc[-1]), 2)
            stats[key] = ma
            stats[f"{key}_diff_pct"] = round((current - ma) / ma * 100, 2)
        else:
            stats[key] = None
            stats[f"{key}_diff_pct"] = None
    if n >= 20:
        high60 = round(float(closes.rolling(min(60, n)).max().iloc[-1]), 2)
        stats["high_recent"] = high60
        stats["high_recent_diff_pct"] = round((current - high60) / high60 * 100, 2)
    return stats


def _fetch_tpex_monthly_api(year, month):
    """
    Fetch TPEX composite index (加權指數) for a specific month via POST.
    API: POST https://www.tpex.org.tw/www/zh-tw/indexInfo/inx
         date=YYYY/MM/01  response=json
    Returns {date_str: close_price} e.g. {"2026-06-01": 446.02, ...}
    """
    date_param = f"{year}/{month:02d}/01"
    url = "https://www.tpex.org.tw/www/zh-tw/indexInfo/inx"
    try:
        r = _session.post(url,
                          data={"date": date_param, "response": "json"},
                          headers={"Referer": "https://www.tpex.org.tw/",
                                   "X-Requested-With": "XMLHttpRequest"},
                          timeout=12)
        data = r.json()
        if data.get("stat") != "ok":
            return {}
        rows = data["tables"][0].get("data", [])
        closes = {}
        for row in rows:
            if len(row) < 5:
                continue
            date_str = str(row[0]).replace("/", "-")   # "2026/06/01" → "2026-06-01"
            try:
                closes[date_str] = round(float(str(row[4]).replace(",", "")), 2)
            except ValueError:
                pass
        if closes:
            print(f"TPEX API {year}/{month:02d}: {len(closes)} days", file=sys.stderr)
        return closes
    except Exception as e:
        print(f"Warning: TPEX API {year}/{month}: {e}", file=sys.stderr)
        return {}


def _accumulate_tpex_history(old_history):
    """
    Build TPEX daily history from tpex.org.tw official API.
    - Loads existing accumulated data from previous JSON
    - Fetches current month (always) + missing historical months (up to 14 months)
    - Computes MA20/60/240 and 近期高點距離 from accumulated data
    Returns (full_history, history_60d, entry_dict_with_ma_stats)
    """
    import pandas as pd
    from datetime import date as _date

    existing = {}
    for d, c in zip(old_history.get("dates", []), old_history.get("closes", [])):
        if d and c is not None:
            existing[d] = c

    today = _date.today()

    # Generate last 14 months (covers ~300 trading days for MA240)
    months = []
    y, m = today.year, today.month
    for _ in range(14):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    for year, month in months:
        prefix = f"{year}-{month:02d}-"
        is_current = (year == today.year and month == today.month)
        # Always refresh current month; skip historical months already in cache
        if is_current or not any(d.startswith(prefix) for d in existing):
            monthly = _fetch_tpex_monthly_api(year, month)
            if monthly:
                existing.update(monthly)

    sorted_dates = sorted(existing.keys())[-300:]
    closes_list  = [existing[d] for d in sorted_dates]

    # Build entry dict (current/prev from latest two dates)
    entry = {"symbol": "TPEX", "current": None}
    if sorted_dates:
        cur  = closes_list[-1]
        prev = closes_list[-2] if len(closes_list) >= 2 else None
        entry.update({
            "current":    cur,
            "prev":       prev,
            "change":     round(cur - prev, 2) if prev else None,
            "change_pct": round((cur - prev) / prev * 100, 2) if prev else None,
            "last_date":  sorted_dates[-1],
        })
        if len(sorted_dates) >= 20:
            entry.update(_compute_ma_stats(pd.Series(closes_list), cur))

    return (
        {"dates": sorted_dates, "closes": closes_list},        # full history for JSON
        {"dates": sorted_dates[-60:], "closes": closes_list[-60:]},  # 60d for chart
        entry,
    )


def fetch_tpex_index():
    """
    Fetch TPEX (台灣上櫃加權指數) with MA20/60/240 and 近期高點 distance.
    Data source: official tpex.org.tw API — correct index values (~430-450 in 2026).
    NOTE: TWSE MIS IX0044 returns a different/incorrect index, do NOT use it.
    """
    old_history = {}
    try:
        if os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                old_json = json.load(f)
            old_history = old_json.get("vix_history", {}).get("tpex", {})
    except Exception:
        pass

    full_history, history_60d, entry = _accumulate_tpex_history(old_history)

    if not entry.get("current"):
        entry = {"symbol": "TPEX", "current": None, "error": "API unavailable"}

    return entry, full_history, history_60d


def fetch_vix_data():
    """Fetch VIX, VIXTWN, Taiwan indices and US major index data."""
    tickers = {
        "vix":    "^VIX",
        "vix9d":  "^VIX9D",
        "vix3m":  "^VIX3M",
        "vix6m":  "^VIX6M",
        "twii":   "^TWII",
        "sp500":  "^GSPC",
        "nasdaq": "^IXIC",
        "dji":    "^DJI",
        "sox":    "^SOX",
        "nikkei": "^N225",
        "kospi":  "^KS11",
    }

    result = {}
    history = {}

    for key, symbol in tickers.items():
        period = "300d" if key in MA_STAT_KEYS else "60d"
        try:
            ticker = yf.Ticker(symbol, session=_session)
            hist = ticker.history(period=period, interval="1d")

            if not hist.empty:
                cur  = round(float(hist["Close"].iloc[-1]), 2)
                prev = round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else None
                entry = {
                    "symbol":     symbol,
                    "current":    cur,
                    "prev":       prev,
                    "change":     round(cur - prev, 2) if prev else 0,
                    "change_pct": round((cur - prev) / prev * 100, 2) if prev else 0,
                    "high_52w":   round(float(hist["Close"].max()), 2),
                    "low_52w":    round(float(hist["Close"].min()), 2),
                }
                if key in MA_STAT_KEYS:
                    entry.update(_compute_ma_stats(hist["Close"], cur))
                # Volume ratio: today vs 60-day max
                if "Volume" in hist.columns:
                    vols = hist["Volume"].dropna()
                    if len(vols) >= 2:
                        v_today = float(vols.iloc[-1])
                        v_max   = float(vols.rolling(min(60, len(vols))).max().iloc[-1])
                        if v_max > 0 and v_today > 0:
                            entry["volume_today"]      = round(v_today, 0)
                            entry["volume_max_recent"] = round(v_max,   0)
                            entry["volume_ratio"]      = round(v_today / v_max * 100, 1)
                result[key] = entry
                history[key] = {
                    "dates":  [str(d.date()) for d in hist.index[-60:]],
                    "closes": [round(float(v), 2) for v in hist["Close"].tolist()[-60:]],
                }
            else:
                result[key] = {"symbol": symbol, "current": None, "error": "no data"}
        except Exception as e:
            result[key] = {"symbol": symbol, "current": None, "error": str(e)}
            print(f"Warning: failed to fetch {symbol}: {e}", file=sys.stderr)

    # Fetch TPEX (OTC) index with history accumulation and MA stats
    tpex_entry, tpex_full_hist, tpex_hist_60d = fetch_tpex_index()
    # Supplement TPEX entry with volume ratio via yfinance ^TWO
    try:
        two_hist = yf.Ticker("^TWO", session=_session).history(period="60d", interval="1d")
        if not two_hist.empty and "Volume" in two_hist.columns:
            vols = two_hist["Volume"].dropna()
            if len(vols) >= 2:
                v_today = float(vols.iloc[-1])
                v_max   = float(vols.rolling(min(60, len(vols))).max().iloc[-1])
                if v_max > 0 and v_today > 0:
                    tpex_entry["volume_today"]      = round(v_today, 0)
                    tpex_entry["volume_max_recent"] = round(v_max,   0)
                    tpex_entry["volume_ratio"]      = round(v_today / v_max * 100, 1)
    except Exception as e:
        print(f"Warning: TPEX ^TWO volume failed: {e}", file=sys.stderr)
    result["tpex"]  = tpex_entry
    history["tpex"] = tpex_full_hist   # full history stored in JSON for future accumulation

    # Fetch VIXTWN from TAIFEX (real-time)
    vixtwn_data = fetch_vixtwn_from_taifex()
    if vixtwn_data:
        result["vixtwn"] = vixtwn_data
    else:
        result["vixtwn"] = {"symbol": "VIXTWN", "current": None, "error": "TAIFEX unavailable"}

    # Build VIXTWN 60-day history via daily accumulation
    history["vixtwn"] = _accumulate_vixtwn_history(result["vixtwn"])

    return result, history


def _scrape_vixtwn_taifex_closes():
    """
    Scrape TAIFEX vixMinNew page for current-month VIXTWN daily closing prices.
    Returns {date_str: close_float} e.g. {"2026-06-30": 38.54, ...}
    Each date file has 15-second ticks; last tick = closing value.
    """
    closes = {}
    try:
        page = _session.get(
            "https://www.taifex.com.tw/cht/7/vixMinNew",
            headers={"Referer": "https://www.taifex.com.tw/"},
            timeout=15,
        )
        import re as _re
        dates = _re.findall(r"getVixData\?filesname=(\d{8})", page.text)
        print(f"VIXTWN history: found {len(dates)} dates on TAIFEX page", file=sys.stderr)
        for d in dates:
            try:
                r = _session.get(
                    f"https://www.taifex.com.tw/cht/7/getVixData?filesname={d}",
                    headers={"Referer": "https://www.taifex.com.tw/cht/7/vixMinNew"},
                    timeout=10,
                )
                txt = r.content.decode("big5", errors="ignore")
                rows = [l.strip() for l in txt.split("\n") if l.strip() and l[0].isdigit()]
                if rows:
                    parts = rows[-1].split("\t")
                    close = float(parts[-1].strip())
                    date_fmt = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                    closes[date_fmt] = round(close, 2)
            except Exception as e:
                print(f"Warning: VIXTWN file {d} error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: VIXTWN history scrape failed: {e}", file=sys.stderr)
    return closes


def _accumulate_vixtwn_history(vixtwn_today):
    """
    Build VIXTWN daily history:
    1. Load existing JSON history (prior months accumulated over time)
    2. Overwrite/update with current-month data scraped from TAIFEX vixMinNew
       (accurate closing ticks, always up to date for current month)
    3. Fill today's live value from REST API if market still open
    Returns sorted last-90-days slice.
    """
    existing = {}

    # Load previously accumulated history (prior months)
    try:
        if os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                old = json.load(f)
            old_h = old.get("vix_history", {}).get("vixtwn", {})
            for d, c in zip(old_h.get("dates", []), old_h.get("closes", [])):
                if d and c is not None:
                    existing[d] = c
    except Exception:
        pass

    # Scrape current-month accurate closes from TAIFEX (overwrites any stale values)
    taifex_closes = _scrape_vixtwn_taifex_closes()
    existing.update(taifex_closes)

    # Also insert today's live REST API value (in case market just closed / page not updated yet)
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    cur = vixtwn_today.get("current") if vixtwn_today else None
    if cur and today not in taifex_closes:
        existing[today] = round(cur, 2)

    # Sort and keep last 90 trading days
    sorted_dates = sorted(existing.keys())[-90:]
    return {
        "dates":  sorted_dates,
        "closes": [existing[d] for d in sorted_dates],
    }


def fetch_cnn_fear_greed():
    """Fetch CNN Fear & Greed Index."""
    # Use a real browser UA — CNN's CDN returns 418 for bot-like UAs.
    # The dataviz endpoint updates ~hourly during US market hours (not at close).
    # Use the date-range variant to pull the most recent data point.
    now_ts = int(datetime.now(timezone.utc).timestamp())
    browser_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    req_headers = {
        "User-Agent": browser_ua,
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        "Origin": "https://edition.cnn.com",
        "Accept": "application/json, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # Try date-range (freshest data), fall back to no-arg endpoint
    urls = [
        f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{now_ts - 86400}/{now_ts}",
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
    ]
    data = None
    for url in urls:
        try:
            resp = _session.get(url, headers=req_headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                break
            print(f"Warning: CNN F&G {url} → HTTP {resp.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: CNN F&G {url} error: {e}", file=sys.stderr)

    if data is None:
        return {"current": None, "rating": "unknown", "error": "all endpoints failed"}

    fg = data.get("fear_and_greed", {})
    historical = data.get("fear_and_greed_historical", {}).get("data", [])

    # Use the most recent historical data point (may be newer than fg.score)
    score = fg.get("score")
    rating = fg.get("rating", "unknown")
    data_ts = fg.get("timestamp")
    if historical:
        last = max(historical, key=lambda p: p.get("x", 0))
        if last.get("y") is not None:
            score = last["y"]
            rating = last.get("rating", rating)
            # Convert ms timestamp to ISO string
            last_ts_s = last["x"] / 1000
            import datetime as _dt
            data_ts = _dt.datetime.utcfromtimestamp(last_ts_s).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Trim historical to last 60 daily data points
    hist_dates  = [item["x"] for item in historical[-60:]]
    hist_values = [round(item["y"], 1) for item in historical[-60:]]

    return {
        "current": round(score, 1) if score is not None else None,
        "rating": rating,
        "data_timestamp": data_ts,
        "prev_close":  round(fg.get("previous_close",  0), 1),
        "prev_1week":  round(fg.get("previous_1_week",  0), 1),
        "prev_1month": round(fg.get("previous_1_month", 0), 1),
        "prev_1year":  round(fg.get("previous_1_year",  0), 1),
        "history_dates":  hist_dates,
        "history_values": hist_values,
    }


def fetch_twse_institutional():
    """Fetch Taiwan Stock Exchange three major institutional investors data."""
    url = "https://www.twse.com.tw/fund/BFI82U"
    params = {"response": "json", "type": "day"}
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MarketDashboard/1.0)",
        "Referer": "https://www.twse.com.tw/",
    }

    try:
        resp = _session.get(url, params=params, headers={"Referer": "https://www.twse.com.tw/"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        rows = data.get("data", [])
        result = {
            "date": data.get("date", ""),
            "title": data.get("title", ""),
            "foreign": None,
            "investment_trust": None,
            "dealer": None,
            "total_net": None,
        }

        def parse_num(s):
            try:
                return int(str(s).replace(",", "").replace("+", ""))
            except Exception:
                return 0

        for row in rows:
            name = str(row[0]).strip()
            # Net buy/sell is column index 3 (買賣超) in NT$ (元)
            # TWSE row format: 外資及陸資(不含外資自營商) / 投信 / 自營商(自行買賣)
            if "外資及陸資" in name or ("外資" in name and "陸資" not in name and "自營商" not in name):
                result["foreign"] = parse_num(row[3])
            elif "投信" in name:
                result["investment_trust"] = parse_num(row[3])
            elif "自營商" in name and "避險" not in name and "外資" not in name:
                result["dealer"] = parse_num(row[3])

        # Total net
        vals = [v for v in [result["foreign"], result["investment_trust"], result["dealer"]] if v is not None]
        result["total_net"] = sum(vals) if vals else None

        # Fetch 30-day history (weekly is enough for trends)
        history = fetch_twse_institutional_history()
        result["history"] = history

        return result

    except Exception as e:
        print(f"Warning: failed to fetch TWSE institutional: {e}", file=sys.stderr)
        return {"error": str(e), "foreign": None, "investment_trust": None, "dealer": None, "total_net": None}


def fetch_twse_institutional_history():
    """
    Fetch last 20 trading days of institutional net buy/sell from BFI82U.
    Queries each trading day individually using the correct `date` parameter.
    """
    import time
    from datetime import date, timedelta

    def parse_num(s):
        try:
            return int(str(s).replace(",", "").replace("+", ""))
        except Exception:
            return 0

    results = []
    today = date.today()
    day = today
    checked = 0

    while len(results) < 20 and checked < 60:
        checked += 1
        if day.weekday() >= 5:        # skip weekends
            day -= timedelta(days=1)
            continue

        date_str = day.strftime("%Y%m%d")
        try:
            resp = _session.get(
                "https://www.twse.com.tw/fund/BFI82U",
                params={"response": "json", "type": "day", "date": date_str},
                headers={"Referer": "https://www.twse.com.tw/"},
                timeout=10,
            )
            data = resp.json()
            rows = data.get("data", [])
            if rows:
                entry = {"date": date_str, "foreign": 0, "investment_trust": 0, "dealer": 0}
                for row in rows:
                    name = str(row[0]).strip()
                    if "外資及陸資" in name or ("外資" in name and "陸資" not in name and "自營商" not in name):
                        entry["foreign"] = parse_num(row[3])
                    elif "投信" in name:
                        entry["investment_trust"] = parse_num(row[3])
                    elif "自營商" in name and "避險" not in name and "外資" not in name:
                        entry["dealer"] = parse_num(row[3])
                entry["total"] = entry["foreign"] + entry["investment_trust"] + entry["dealer"]
                results.append(entry)
        except Exception as e:
            print(f"Warning: BFI82U {date_str}: {e}", file=sys.stderr)

        day -= timedelta(days=1)
        time.sleep(0.15)   # avoid rate-limiting

    results.reverse()
    print(f"BFI82U history: {len(results)} days", file=sys.stderr)
    return results


def compute_market_signal(vix_data, cnn_data, institutional_data):
    """
    Compute composite market signal score (-100 to +100).
    Positive = bullish for Taiwan market, Negative = bearish.
    """
    scores = {}
    details = []

    # --- VIXTWN signal (weight 30%) ---
    vixtwn_val = vix_data.get("vixtwn", {}).get("current")
    if vixtwn_val is not None:
        if vixtwn_val >= 30:
            s = 70   # Extreme fear = strong contrarian buy
            label = f"台灣VIX極度恐慌({vixtwn_val:.1f}≥30)：逆向強買訊號"
        elif vixtwn_val >= 25:
            s = 40
            label = f"台灣VIX恐慌({vixtwn_val:.1f}≥25)：買入訊號"
        elif vixtwn_val >= 20:
            s = 10
            label = f"台灣VIX偏高({vixtwn_val:.1f}≥20)：謹慎中性偏多"
        elif vixtwn_val >= 15:
            s = 0
            label = f"台灣VIX正常({vixtwn_val:.1f}：15-20)：中性"
        elif vixtwn_val >= 12:
            s = -20
            label = f"台灣VIX偏低({vixtwn_val:.1f}：12-15)：市場過度樂觀，輕度賣出警示"
        else:
            s = -50
            label = f"台灣VIX極低({vixtwn_val:.1f}<12)：市場極度貪婪，強烈賣出警示"
        scores["vixtwn"] = s * 0.30
        details.append({"indicator": "VIXTWN", "value": vixtwn_val, "signal": s, "label": label, "weight": "30%"})

    # --- US VIX signal (weight 15%) ---
    vix_val = vix_data.get("vix", {}).get("current")
    if vix_val is not None:
        if vix_val >= 35:
            s = 60
            label = f"美股VIX恐慌({vix_val:.1f}≥35)：市場重度避險，等待反彈"
        elif vix_val >= 25:
            s = 30
            label = f"美股VIX偏高({vix_val:.1f}≥25)：市場擔憂，短期偏多"
        elif vix_val >= 18:
            s = 5
            label = f"美股VIX正常({vix_val:.1f}：18-25)：中性"
        elif vix_val >= 13:
            s = -15
            label = f"美股VIX偏低({vix_val:.1f}：13-18)：輕度過熱"
        else:
            s = -40
            label = f"美股VIX極低({vix_val:.1f}<13)：市場極度自滿"
        scores["vix"] = s * 0.15
        details.append({"indicator": "US VIX", "value": vix_val, "signal": s, "label": label, "weight": "15%"})

    # --- VIX Term Structure signal (weight 15%) ---
    vix9d = vix_data.get("vix9d", {}).get("current")
    vix3m = vix_data.get("vix3m", {}).get("current")
    vix6m = vix_data.get("vix6m", {}).get("current")

    if vix9d and vix_val and vix3m:
        if vix9d > vix_val * 1.10:
            s = 50   # Strongly inverted = panic
            label = f"VIX期限結構強烈倒掛(VIX9D {vix9d:.1f} >> VIX {vix_val:.1f})：短期恐慌劇烈，可能觸底"
        elif vix9d > vix_val:
            s = 25
            label = f"VIX期限結構輕度倒掛(VIX9D {vix9d:.1f} > VIX {vix_val:.1f})：短期壓力偏大"
        elif vix3m > vix6m if vix6m else False:
            s = -10
            label = f"VIX期限結構正常偏陡(3M>{vix3m:.1f}>6M)：市場平穩"
        else:
            s = -15  # Normal contango = complacency
            label = f"VIX期限結構正常順向(VIX9D {vix9d:.1f} < VIX {vix_val:.1f} < 3M {vix3m:.1f})：市場自滿"
        scores["term_structure"] = s * 0.15
        details.append({"indicator": "VIX期限結構", "value": round(vix9d - vix_val, 2), "signal": s, "label": label, "weight": "15%"})

    # --- CNN Fear & Greed signal (weight 15%) ---
    cnn_score = cnn_data.get("current")
    if cnn_score is not None:
        if cnn_score <= 25:
            s = 60   # Extreme Fear = buy
            label = f"CNN極度恐懼({cnn_score:.0f}≤25)：歷史底部區域，逆向做多"
        elif cnn_score <= 45:
            s = 25
            label = f"CNN恐懼({cnn_score:.0f}：26-45)：市場偏悲觀，偏多"
        elif cnn_score <= 55:
            s = 0
            label = f"CNN中性({cnn_score:.0f}：46-55)：市場情緒平衡"
        elif cnn_score <= 75:
            s = -25
            label = f"CNN貪婪({cnn_score:.0f}：56-75)：市場過熱，降低倉位"
        else:
            s = -60
            label = f"CNN極度貪婪({cnn_score:.0f}>75)：泡沫警示，考慮避險"
        scores["cnn"] = s * 0.15
        details.append({"indicator": "CNN恐懼貪婪", "value": cnn_score, "signal": s, "label": label, "weight": "15%"})

    # --- Institutional investor signal (weight 25%) ---
    inst_total = institutional_data.get("total_net")
    if inst_total is not None:
        billions = inst_total / 100000000  # 轉換為億元 (1億=1e8)
        if billions > 100:
            s = 80
            label = f"三大法人合計大買({billions:.1f}億)：強力護盤，多方訊號"
        elif billions > 30:
            s = 40
            label = f"三大法人合計淨買({billions:.1f}億)：法人偏多"
        elif billions > -30:
            s = 5
            label = f"三大法人接近中性({billions:.1f}億)：觀望"
        elif billions > -100:
            s = -40
            label = f"三大法人合計淨賣({billions:.1f}億)：法人偏空"
        else:
            s = -70
            label = f"三大法人大量賣出({billions:.1f}億)：空方強勢"
        scores["institutional"] = s * 0.25
        details.append({"indicator": "三大法人", "value": round(billions, 1), "signal": s, "label": label, "weight": "25%"})

    # Total weighted score
    total_score = sum(scores.values())
    total_score = max(-100, min(100, total_score))

    # Market outlook
    if total_score >= 50:
        outlook = "強力做多"
        outlook_en = "STRONG BUY"
        color = "#00e676"
    elif total_score >= 20:
        outlook = "偏多"
        outlook_en = "BUY"
        color = "#69f0ae"
    elif total_score >= -20:
        outlook = "中性觀望"
        outlook_en = "NEUTRAL"
        color = "#ffc107"
    elif total_score >= -50:
        outlook = "偏空"
        outlook_en = "SELL"
        color = "#ff7043"
    else:
        outlook = "強力做空"
        outlook_en = "STRONG SELL"
        color = "#f44336"

    return {
        "score": round(total_score, 1),
        "outlook": outlook,
        "outlook_en": outlook_en,
        "color": color,
        "details": details,
        "component_scores": {k: round(v, 2) for k, v in scores.items()},
    }


def generate_expert_analysis(vix_data, cnn_data, institutional_data, signal):
    """Generate natural language expert analysis in Traditional Chinese."""
    lines = []

    vixtwn = vix_data.get("vixtwn", {}).get("current")
    vix = vix_data.get("vix", {}).get("current")
    vix9d = vix_data.get("vix9d", {}).get("current")
    vix3m = vix_data.get("vix3m", {}).get("current")
    twii = vix_data.get("twii", {}).get("current")
    cnn = cnn_data.get("current")
    cnn_rating = cnn_data.get("rating", "")
    inst_total = institutional_data.get("total_net")
    foreign = institutional_data.get("foreign")
    inv_trust = institutional_data.get("investment_trust")
    dealer = institutional_data.get("dealer")

    score = signal["score"]
    outlook = signal["outlook"]

    lines.append("【市場總覽】")
    if twii:
        lines.append(f"台股加權指數目前報 {twii:,.0f} 點。")

    lines.append("")
    lines.append("【波動率分析】")
    if vixtwn:
        level = "極度恐慌" if vixtwn >= 30 else "恐慌" if vixtwn >= 25 else "偏高" if vixtwn >= 20 else "正常" if vixtwn >= 15 else "偏低"
        lines.append(f"台灣VIX（VIXTWN）目前為 {vixtwn:.2f}，處於{level}水準。")
    if vix:
        us_level = "極度恐慌" if vix >= 35 else "恐慌" if vix >= 25 else "偏高" if vix >= 18 else "正常" if vix >= 13 else "過度自滿"
        lines.append(f"美股VIX目前為 {vix:.2f}，市場情緒{us_level}。")
    if vix9d and vix and vix3m:
        if vix9d > vix:
            lines.append(f"VIX期限結構呈倒掛（VIX9D={vix9d:.2f} > VIX={vix:.2f}），代表短期市場恐慌情緒高於中期，顯示可能為短線恐慌性賣壓，歷史上此情形後續往往出現反彈。")
        else:
            lines.append(f"VIX期限結構正常順向（VIX9D={vix9d:.2f} < VIX={vix:.2f} < VIX3M={vix3m:.2f}），市場處於相對平靜狀態。")

    lines.append("")
    lines.append("【市場情緒分析】")
    if cnn is not None:
        rating_map = {
            "extreme fear": "極度恐懼",
            "fear": "恐懼",
            "neutral": "中性",
            "greed": "貪婪",
            "extreme greed": "極度貪婪",
        }
        rating_zh = rating_map.get(cnn_rating.lower(), cnn_rating)
        lines.append(f"CNN恐懼貪婪指數目前為 {cnn:.0f}（{rating_zh}）。")
        if cnn <= 25:
            lines.append("當前處於極度恐懼區間，歷史數據顯示此為長期買入良機，建議分批佈局。")
        elif cnn <= 45:
            lines.append("市場偏向悲觀，但未達極端，可逐步加碼。")
        elif cnn <= 55:
            lines.append("市場情緒中性，建議持倉觀望，等待方向明確。")
        elif cnn <= 75:
            lines.append("市場偏向貪婪，需留意回調風險，可適度降低槓桿。")
        else:
            lines.append("市場處於極度貪婪區間，歷史上此時回調機率大幅提升，建議減碼或避險。")

    lines.append("")
    lines.append("【三大法人動向】")
    if inst_total is not None:
        b = inst_total / 100000000
        lines.append(f"今日三大法人合計{'買超' if b >= 0 else '賣超'} {abs(b):.1f} 億元。")
        if foreign is not None:
            fb = foreign / 100000000
            lines.append(f"  • 外資：{'買超' if fb >= 0 else '賣超'} {abs(fb):.1f} 億元（市場主力，對台股方向影響最大）")
        if inv_trust is not None:
            ib = inv_trust / 100000000
            lines.append(f"  • 投信：{'買超' if ib >= 0 else '賣超'} {abs(ib):.1f} 億元（國內基金動向，反映內資信心）")
        if dealer is not None:
            db = dealer / 100000000
            lines.append(f"  • 自營商：{'買超' if db >= 0 else '賣超'} {abs(db):.1f} 億元（短線交易為主，可作輔助參考）")

    lines.append("")
    lines.append("【綜合研判】")
    lines.append(f"綜合波動率指標、市場情緒及法人動向，本系統計算綜合信號分數為 {score:+.1f} 分（滿分 ±100），")
    lines.append(f"目前市場判斷為「{outlook}」。")

    if score >= 50:
        lines.append("多項指標同步發出強烈買入訊號，建議積極做多，可適度提高倉位。惟請注意設置停損，市場反轉時需快速應對。")
    elif score >= 20:
        lines.append("整體訊號偏多，可逐步建立多頭部位，但勿過度集中，建議搭配個股選擇及風險控管。")
    elif score >= -20:
        lines.append("市場訊號混合，建議維持現有倉位，耐心等待更明確的方向突破。可關注成交量及外資動向變化。")
    elif score >= -50:
        lines.append("多項指標偏空，建議降低倉位，持有防禦性資產，謹慎操作。")
    else:
        lines.append("多項指標同步發出強烈賣出訊號，建議大幅降低倉位或進行避險操作，保留現金等待更佳入場時機。")

    lines.append("")
    lines.append("⚠️ 本分析僅供參考，不構成投資建議。投資有風險，入市需謹慎。")

    return "\n".join(lines)


def fetch_drai_holdings():
    """
    Scrape DRAI ETF Fund Holdings from draietf.com/etf/.
    Returns {as_of, holdings: [{ticker, weight_pct}]} or None on failure.
    """
    try:
        from bs4 import BeautifulSoup
        r = _session.get("https://draietf.com/etf/", timeout=15,
                         headers={"Referer": "https://draietf.com/"})
        soup = BeautifulSoup(r.text, "html.parser")

        # Find the holdings table — look for a table with a Ticker column header
        table = None
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
            if "ticker" in headers and any("net" in h or "weight" in h or "%" in h for h in headers):
                table = t
                break
            if "ticker" in headers and len(headers) >= 5:
                table = t
                break

        if not table:
            print("Warning: DRAI holdings table not found", file=sys.stderr)
            return None

        # Map column indices
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        try:
            ticker_idx = next(i for i, h in enumerate(headers) if "ticker" in h)
        except StopIteration:
            ticker_idx = 0
        # % of Net Assets or weight column
        try:
            weight_idx = next(i for i, h in enumerate(headers) if "net" in h or "weight" in h or h.startswith("%"))
        except StopIteration:
            weight_idx = len(headers) - 2  # second-to-last fallback
        # Effective date column
        try:
            date_idx = next(i for i, h in enumerate(headers) if "date" in h or "effective" in h)
        except StopIteration:
            date_idx = None

        holdings = []
        as_of = None
        for row in table.find("tbody").find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells or len(cells) <= max(ticker_idx, weight_idx):
                continue
            ticker = cells[ticker_idx].strip()
            if not ticker:
                continue
            try:
                weight = float(cells[weight_idx].replace("%", "").replace(",", ""))
            except ValueError:
                continue
            holdings.append({"ticker": ticker, "weight": round(weight, 2)})
            if date_idx and not as_of and date_idx < len(cells):
                as_of = cells[date_idx].strip()

        if not holdings:
            return None

        holdings.sort(key=lambda x: x["weight"], reverse=True)
        print(f"DRAI holdings: {len(holdings)} positions, as_of={as_of}", file=sys.stderr)
        return {"as_of": as_of, "holdings": holdings}

    except Exception as e:
        print(f"Warning: fetch_drai_holdings failed: {e}", file=sys.stderr)
        return None


# ─── TWSE / TPEX Heatmap ─────────────────────────────────────────────────────

# Top TWSE (上市) stocks: code → (shares_billions, display_name, sector)
_HM_TWSE = {
    "2330": (259.3, "台積電", "半導體"),
    "2454": ( 15.6, "聯發科", "半導體"),
    "2303": (242.4, "聯電",   "半導體"),
    "3711": ( 75.8, "日月光", "半導體"),
    "3008": (  1.34,"大立光", "半導體"),
    "2379": ( 10.5, "瑞昱",   "半導體"),
    "2317": (138.6, "鴻海",   "電子"),
    "2308": ( 25.9, "台達電", "電子"),
    "2382": ( 25.2, "廣達",   "電子"),
    "2357": ( 13.5, "華碩",   "電子"),
    "3231": ( 38.3, "緯創",   "電子"),
    "2324": ( 42.5, "仁寶",   "電子"),
    "2345": (  8.3, "智邦",   "電子"),
    "2881": (106.0, "富邦金", "金融"),
    "2882": (141.2, "國泰金", "金融"),
    "2891": (193.2, "中信金", "金融"),
    "2886": ( 97.4, "兆豐金", "金融"),
    "2884": (182.1, "玉山金", "金融"),
    "2885": (152.9, "元大金", "金融"),
    "2892": (112.1, "第一金", "金融"),
    "5880": (161.6, "合庫金", "金融"),
    "1301": ( 63.6, "台塑",   "石化"),
    "1303": ( 78.1, "南亞",   "石化"),
    "2002": (157.5, "中鋼",   "鋼鐵"),
    "2412": ( 77.6, "中華電", "電信"),
    "3045": ( 33.6, "台灣大", "電信"),
    "4904": ( 33.6, "遠傳",   "電信"),
    "2603": ( 37.9, "長榮",   "航運"),
    "2609": ( 30.2, "陽明",   "航運"),
    "1216": ( 56.8, "統一",   "消費"),
}

# Top TPEX (上櫃) stocks: code → (shares_billions, display_name, sector)
_HM_TPEX = {
    "3034": (1.26, "聯詠",  "半導體"),
    "6415": (0.72, "矽力",  "半導體"),
    "3529": (0.55, "力旺",  "半導體"),
    "6223": (1.00, "旺矽",  "半導體"),
    "5274": (0.30, "信驊",  "半導體"),
    "5269": (0.46, "祥碩",  "半導體"),
    "3661": (0.53, "世芯",  "半導體"),
    "8299": (0.42, "群聯",  "半導體"),
    "4919": (0.54, "新唐",  "半導體"),
    "3702": (0.86, "大聯大","通路"),
    "3596": (0.46, "智易",  "網通"),
    "5388": (0.45, "中磊",  "網通"),
    "3533": (0.56, "嘉澤",  "連接器"),
    "6269": (0.84, "台郡",  "軟板"),
    "3081": (0.27, "聯亞",  "半導體"),
}


def _fetch_twse_all_stocks():
    """
    Fetch all TWSE daily data from STOCK_DAY_ALL.
    The endpoint returns CSV (not JSON) regardless of ?response=json.
    Columns: 日期, 代號, 名稱, 成交股數, 成交金額, 開盤, 最高, 最低, 收盤, 漲跌價差, 成交筆數
    Returns (dict: code → {close, change_pct, vol_value}, as_of_str)
    """
    import csv, io
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL"
    try:
        r = _session.get(url, timeout=25)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        result = {}
        as_of = None
        for row in reader:
            if len(row) < 10:
                continue
            date_field = row[0].strip()
            # Skip header rows (non-numeric first field)
            if not date_field[:3].replace('"', '').isdigit():
                continue
            code = row[1].strip()
            # Only 4-digit numeric codes starting 1-9 (exclude ETFs like 0050)
            if not (len(code) == 4 and code.isdigit() and code[0] != '0'):
                continue
            try:
                close = float(row[8].replace(",", ""))
                change_str = row[9].replace(",", "").replace("+", "").strip()
                if change_str in ("", "X", "--", "—", "除息", "除權"):
                    change = 0.0
                else:
                    change = float(change_str)
                vol_value = float(row[4].replace(",", ""))
                prev = close - change
                change_pct = round(change / prev * 100, 2) if abs(prev) > 0.01 else 0.0
                result[code] = {
                    "close":      close,
                    "change_pct": change_pct,
                    "vol_value":  vol_value,
                    "name":       row[2].strip(),
                }
                # Parse ROC date to CE date once
                if not as_of and len(date_field) == 7 and date_field.isdigit():
                    yr = int(date_field[:3]) + 1911
                    as_of = f"{yr}/{date_field[3:5]}/{date_field[5:7]}"
            except (ValueError, ZeroDivisionError):
                continue
        print(f"TWSE STOCK_DAY_ALL: parsed {len(result)} stocks, as_of={as_of}", file=sys.stderr)
        return result, as_of
    except Exception as e:
        print(f"Warning: _fetch_twse_all_stocks failed: {e}", file=sys.stderr)
        return {}, None


def _fetch_twse_inst_per_stock():
    """
    Fetch per-stock institutional buy/sell from TWSE T86 (today or latest available day).
    Returns dict: code → {foreign_net, trust_net, total_net}  (shares, positive = net buy)
    """
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    try:
        r = _session.get(url, params={"response": "json", "selectType": "ALL"}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Warning: T86 per-stock failed: {e}", file=sys.stderr)
        return {}

    if data.get("stat") != "OK":
        return {}

    fields = [f.replace(" ", "").replace("\n", "") for f in data.get("fields", [])]

    def find_col(*keywords):
        for i, f in enumerate(fields):
            if all(k in f for k in keywords):
                return i
        return None

    # 外資淨 (excluding 外資自營): first col whose name has 外資+淨 but NOT 自營
    col_foreign = None
    for i, f in enumerate(fields):
        if "外資" in f and "淨" in f and "自營" not in f:
            col_foreign = i
            break
    col_trust = find_col("投信", "淨")
    col_total = find_col("三大法人")
    if col_foreign is None: col_foreign = 4
    if col_trust   is None: col_trust   = 10
    if col_total   is None: col_total   = 17

    def parse_shares(s):
        try:
            return int(float(str(s).replace(",", "").replace("+", "").strip()))
        except (ValueError, AttributeError):
            return 0

    result = {}
    for row in data.get("data", []):
        if len(row) < 3:
            continue
        code = str(row[0]).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue
        try:
            f_net = parse_shares(row[col_foreign]) if col_foreign < len(row) else 0
            t_net = parse_shares(row[col_trust])   if col_trust   < len(row) else 0
            total = parse_shares(row[col_total])   if col_total   < len(row) else f_net + t_net
            result[code] = {"foreign_net": f_net, "trust_net": t_net, "total_net": total}
        except (IndexError, ValueError):
            continue

    print(f"T86 per-stock: {len(result)} stocks", file=sys.stderr)
    return result


def _fetch_twse_valuation():
    """
    Fetch P/E, dividend yield, P/B for all TWSE stocks from BWIBBU_d.
    Returns dict: code → {pe, div_yield, pb}
    """
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
    try:
        r = _session.get(url, params={"response": "json", "selectType": "ALL"}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Warning: BWIBBU_d failed: {e}", file=sys.stderr)
        return {}

    if data.get("stat") != "OK":
        return {}

    def parse_num(s):
        try:
            v = float(str(s).replace(",", "").strip())
            return v if v > 0 else None
        except (ValueError, AttributeError):
            return None

    result = {}
    for row in data.get("data", []):
        if len(row) < 5:
            continue
        code = str(row[0]).strip()
        if not (len(code) == 4 and code.isdigit() and code[0] != '0'):
            continue
        result[code] = {
            "pe":        parse_num(row[2]),
            "div_yield": parse_num(row[3]),
            "pb":        parse_num(row[4]),
        }

    print(f"BWIBBU_d: {len(result)} stocks", file=sys.stderr)
    return result


def _fetch_hm_stocks_mis():
    """
    Fetch real-time quotes for all curated heatmap stocks via mis.twse.com.tw.
    Single request covering TWSE stocks (tse_) and TPEX stocks (both tse_ and
    otc_ prefixes, since some _HM_TPEX stocks have been promoted to TWSE).
    Returns (dict: code → {close, change_pct, vol_value (TWD)}, as_of_str or None)
    """
    parts  = [f"tse_{c}.tw" for c in _HM_TWSE]
    for c in _HM_TPEX:
        parts.append(f"tse_{c}.tw")   # needed if promoted to TWSE main board
        parts.append(f"otc_{c}.tw")   # original OTC listing
    ex_ch = "|".join(parts)

    url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    try:
        r = _session.get(url, params={"ex_ch": ex_ch, "json": "1", "delay": "0"}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Warning: MIS heatmap API failed: {e}", file=sys.stderr)
        return {}, None

    result = {}
    as_of  = None
    for item in data.get("msgArray", []):
        code  = item.get("c") or ""
        if not code:
            continue
        y_str = item.get("y") or ""
        z_str = item.get("z") or ""
        if not y_str or y_str in ("-", "N/A"):
            continue
        try:
            prev  = float(y_str.replace(",", ""))
            close = float(z_str.replace(",", "")) if z_str and z_str not in ("-", "N/A") else prev
        except (ValueError, AttributeError):
            continue
        if close <= 0 or prev <= 0:
            continue
        change_pct = round((close - prev) / prev * 100, 2) if abs(prev) > 0.01 else 0.0
        v_str = item.get("v") or "0"
        try:
            vol_lots  = float(str(v_str).replace(",", ""))
            vol_value = vol_lots * 1000 * close
        except (ValueError, AttributeError):
            vol_value = 0.0
        # Keep first hit per code (tse_ wins over otc_ for promoted stocks)
        if code not in result:
            result[code] = {
                "close":      round(close, 2),
                "change_pct": change_pct,
                "vol_value":  round(vol_value, 0),
            }
        if not as_of:
            d_str = item.get("d") or ""
            t_str = item.get("t") or ""
            if d_str and len(d_str) == 8 and d_str.isdigit():
                as_of = f"{d_str[:4]}/{d_str[4:6]}/{d_str[6:]}"
                if t_str and len(t_str) >= 5:
                    as_of += f" {t_str[:5]}"

    n_tw = sum(1 for c in _HM_TWSE if c in result)
    n_tp = sum(1 for c in _HM_TPEX if c in result)
    print(f"MIS heatmap: TWSE {n_tw}/{len(_HM_TWSE)}, TPEX {n_tp}/{len(_HM_TPEX)}, as_of={as_of}", file=sys.stderr)
    return result, as_of


def _fetch_tpex_stk_d():
    """
    Fetch all TPEX (上櫃) mainboard daily close data from TPEX stk_d API.
    Provides official 成交金額 (櫃買成交額) for every 上櫃 stock.
    Returns dict: code → {close, change_pct, vol_value (元, official), name}
    """
    url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_d.php"
    try:
        r = _session.get(url, params={"l": "zh-tw", "o": "json"}, timeout=25)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Warning: TPEX stk_d failed: {e}", file=sys.stderr)
        return {}

    result = {}
    for row in data.get("aaData", []):
        if len(row) < 9:
            continue
        code = str(row[0]).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue
        try:
            close_str = str(row[2]).replace(",", "").strip()
            if not close_str or close_str in ("--", "---"):
                continue
            close = float(close_str)
            if close <= 0:
                continue
            # 漲跌 field may use △/▲/▼ prefixes or +/-
            change_str = (str(row[3]).replace(",", "")
                          .replace("▲", "").replace("△", "").replace("+", "")
                          .replace("▼", "-").strip())
            if change_str in ("", "---", "--", "除息", "除權", "X"):
                change = 0.0
            else:
                change = float(change_str)
            prev = close - change
            change_pct = round(change / prev * 100, 2) if abs(prev) > 0.01 else 0.0
            # col[8]: 成交金額 in 元 (official 櫃買成交額)
            vol_value = float(str(row[8]).replace(",", "") or "0")
            result[code] = {
                "close":      round(close, 2),
                "change_pct": change_pct,
                "vol_value":  vol_value,
                "name":       str(row[1]).strip(),
            }
        except (ValueError, ZeroDivisionError, IndexError):
            continue

    print(f"TPEX stk_d: parsed {len(result)} stocks", file=sys.stderr)
    return result


def fetch_heatmap_data(twse_raw_override=None):
    """
    Build heatmap data for TWSE and TPEX top stocks.
    Primary source: MIS real-time API (every 30-min during trading hours).
    Fallback:       TWSE STOCK_DAY_ALL (post-market) when MIS coverage is poor.
    Extra 上櫃 stocks: TPEX stk_d.php (for dynamic top-vol selection).
    cap/vol stored in 億元 (100 million TWD).
    twse_raw_override: pre-fetched STOCK_DAY_ALL dict to avoid double-fetching.
    Returns {as_of, twse: [...], tpex: [...]}
    """
    mis_raw, mis_as_of = _fetch_hm_stocks_mis()

    # Only call the heavy STOCK_DAY_ALL endpoint if MIS misses most TWSE stocks
    twse_fb, post_as_of = {}, None
    if sum(1 for c in _HM_TWSE if c in mis_raw) < len(_HM_TWSE) // 2:
        if twse_raw_override is not None:
            twse_fb, post_as_of = twse_raw_override, None
        else:
            twse_fb, post_as_of = _fetch_twse_all_stocks()

    tpex_stk_d = _fetch_tpex_stk_d()   # extra top-vol 上櫃 stocks

    as_of = mis_as_of or post_as_of

    def best(code, is_tpex=False):
        if code in mis_raw:
            return mis_raw[code]
        if code in twse_fb:
            return twse_fb[code]
        if is_tpex and code in tpex_stk_d:
            return tpex_stk_d[code]
        return None

    twse_list = []
    for code, (shares_b, name, sector) in _HM_TWSE.items():
        d = best(code)
        if not d:
            continue
        cap = round(shares_b * d["close"], 1)
        vol = round(d["vol_value"] / 1e8, 2)
        twse_list.append({
            "code": code, "name": name, "sector": sector,
            "close": d["close"], "change_pct": d["change_pct"],
            "cap": cap, "vol": vol,
        })
    twse_list.sort(key=lambda x: x["cap"], reverse=True)

    tpex_seen = set()
    tpex_list = []

    for code, (shares_b, name, sector) in _HM_TPEX.items():
        d = best(code, is_tpex=True)
        if not d:
            continue
        cap = round(shares_b * d["close"], 1)
        vol = round(d["vol_value"] / 1e8, 2)
        tpex_list.append({
            "code": code, "name": name, "sector": sector,
            "close": round(d["close"], 2), "change_pct": d["change_pct"],
            "cap": cap, "vol": vol,
        })
        tpex_seen.add(code)

    # Extra top-volume 上櫃 stocks; cap=0 → invisible in market-cap heatmap
    extra = sorted(
        ((c, d) for c, d in tpex_stk_d.items() if c not in tpex_seen and d["vol_value"] > 0),
        key=lambda x: x[1]["vol_value"], reverse=True,
    )
    for code, d in extra[:15]:
        tpex_list.append({
            "code": code, "name": d["name"], "sector": "上櫃",
            "close": d["close"], "change_pct": d["change_pct"],
            "cap": 0,
            "vol": round(d["vol_value"] / 1e8, 2),
        })

    tpex_list.sort(key=lambda x: x["cap"], reverse=True)
    return {"as_of": as_of, "twse": twse_list, "tpex": tpex_list}


def scan_stock_opportunities(twse_raw):
    """
    Post-market stock scan. Scores each stock on:
      Technical  (0-50): MA trend, RSI, MACD, volume breakout, 20d momentum
      Chip       (0-30): foreign/trust institutional net buy from T86
      Valuation  (0-20): P/E and dividend yield from BWIBBU_d
    Returns {as_of, candidates: [top 20 sorted by total score]}
    """
    import pandas as pd

    if not twse_raw:
        return {"as_of": None, "candidates": []}

    # Universe: top 120 liquid stocks (close ≥ 20 TWD, 成交金額 ≥ 2億)
    universe = sorted(
        [c for c, d in twse_raw.items()
         if d.get("close", 0) >= 20 and d.get("vol_value", 0) >= 2e8],
        key=lambda c: twse_raw[c]["vol_value"], reverse=True
    )[:120]
    print(f"[Scan] Universe: {len(universe)} stocks", file=sys.stderr)
    if not universe:
        return {"as_of": None, "candidates": []}

    # Batch-download 90d Close + Volume via yfinance
    tickers  = [f"{c}.TW" for c in universe]
    hist_data = {}
    try:
        df = yf.download(tickers, period="90d", interval="1d",
                         auto_adjust=True, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                lvl      = df.columns.get_level_values(0)
                close_df = df.xs("Close",  axis=1, level=0) if "Close"  in lvl else pd.DataFrame()
                vol_df   = df.xs("Volume", axis=1, level=0) if "Volume" in lvl else pd.DataFrame()
            else:
                close_df = df[["Close" ]].rename(columns={"Close" : tickers[0]}) if "Close"  in df.columns else pd.DataFrame()
                vol_df   = df[["Volume"]].rename(columns={"Volume": tickers[0]}) if "Volume" in df.columns else pd.DataFrame()

            for code, ticker in zip(universe, tickers):
                try:
                    c = close_df[ticker].dropna() if ticker in close_df.columns else pd.Series(dtype=float)
                    v = vol_df[ticker].dropna()   if ticker in vol_df.columns   else pd.Series(dtype=float)
                    if len(c) >= 20:
                        hist_data[code] = {"close": c, "vol": v}
                except (KeyError, AttributeError):
                    pass
    except Exception as e:
        print(f"[Scan] Batch history error: {e}", file=sys.stderr)

    print(f"[Scan] History for {len(hist_data)}/{len(universe)} stocks", file=sys.stderr)

    inst_data = _fetch_twse_inst_per_stock()
    val_data  = _fetch_twse_valuation()
    candidates = []

    for code in universe:
        if code not in hist_data:
            continue
        d      = twse_raw[code]
        closes = hist_data[code]["close"]
        vols   = hist_data[code]["vol"]
        n      = len(closes)
        cur    = float(closes.iloc[-1])

        # ── Technical (max 50) ──
        tech = 0; tech_sigs = []
        ma20 = float(closes.iloc[-20:].mean()) if n >= 20 else None
        ma60 = float(closes.iloc[-60:].mean()) if n >= 60 else None

        if ma20 and cur > ma20: tech += 5
        if ma60 and cur > ma60: tech += 5
        if ma20 and ma60 and ma20 > ma60:
            tech += 8; tech_sigs.append("多頭排列")

        if n >= 16:
            delta = closes.diff().dropna()
            gain  = delta.clip(lower=0).rolling(14).mean().iloc[-1]
            loss  = (-delta).clip(lower=0).rolling(14).mean().iloc[-1]
            if loss > 0:
                rsi = 100 - 100 / (1 + gain / loss)
                if   50 <= rsi <= 70: tech += 10; tech_sigs.append(f"RSI{rsi:.0f}")
                elif 45 <= rsi < 50:  tech += 5

        if n >= 30:
            ema12 = float(closes.ewm(span=12, adjust=False).mean().iloc[-1])
            ema26 = float(closes.ewm(span=26, adjust=False).mean().iloc[-1])
            if ema12 > ema26: tech += 4; tech_sigs.append("MACD↑")

        if len(vols) >= 21:
            v0 = float(vols.iloc[-1])
            va = float(vols.iloc[-21:-1].mean())
            if va > 0 and v0 > va * 1.5:
                tech += 8; tech_sigs.append(f"量增{v0/va:.1f}×")

        if n >= 21:
            ret20 = (cur / float(closes.iloc[-21]) - 1) * 100
            if   ret20 > 8: tech += 10; tech_sigs.append(f"↑{ret20:.0f}%")
            elif ret20 > 4: tech += 6
            elif ret20 > 0: tech += 3

        tech = min(50, tech)

        # ── Chip (max 30) ──
        chip = 0; chip_sigs = []
        inst  = inst_data.get(code, {})
        f_net = inst.get("foreign_net", 0)
        t_net = inst.get("trust_net",   0)

        if f_net > 0:        chip += 8;  chip_sigs.append("外資↑")
        if f_net >= 500_000: chip += 4
        if t_net > 0:        chip += 8;  chip_sigs.append("投信↑")
        if t_net >= 100_000: chip += 4
        if f_net > 0 and t_net > 0:
            chip += 6; chip_sigs.append("法人雙買")
        chip = min(30, chip)

        # ── Valuation (max 20) ──
        val = 0; val_sigs = []
        vd  = val_data.get(code, {})
        pe  = vd.get("pe")
        div = vd.get("div_yield")

        if pe is not None:
            if   0 < pe <= 15:  val += 10; val_sigs.append(f"PE{pe:.0f}")
            elif 15 < pe <= 25: val += 5
        if div is not None:
            if   div >= 4:  val += 10; val_sigs.append(f"殖{div:.1f}%")
            elif div >= 2:  val += 5
        val = min(20, val)

        total = tech + chip + val
        if total < 35 or tech < 15:
            continue

        candidates.append({
            "code":        code,
            "name":        d.get("name", code),
            "close":       d["close"],
            "change_pct":  d["change_pct"],
            "vol_b":       round(d["vol_value"] / 1e8, 1),
            "tech_score":  tech,
            "chip_score":  chip,
            "val_score":   val,
            "total_score": total,
            "signals":     tech_sigs + chip_sigs + val_sigs,
            "pe":          pe,
            "div_yield":   div,
        })

    candidates.sort(key=lambda x: x["total_score"], reverse=True)
    print(f"[Scan] {len(candidates)} candidates → top 20", file=sys.stderr)

    as_of = datetime.now(TW_TZ).strftime("%Y/%m/%d %H:%M")
    return {"as_of": as_of, "candidates": candidates[:20]}


def main():
    print("Fetching VIX data...", file=sys.stderr)
    vix_data, vix_history = fetch_vix_data()

    print("Fetching CNN Fear & Greed...", file=sys.stderr)
    cnn_data = fetch_cnn_fear_greed()

    print("Fetching TWSE institutional data...", file=sys.stderr)
    institutional_data = fetch_twse_institutional()

    print("Fetching DRAI ETF holdings...", file=sys.stderr)
    drai_data = fetch_drai_holdings()

    print("Fetching TWSE all-stock data...", file=sys.stderr)
    twse_all, _ = _fetch_twse_all_stocks()

    print("Fetching Taiwan stock heatmap data...", file=sys.stderr)
    heatmap_data = fetch_heatmap_data(twse_raw_override=twse_all)

    print("Running post-market stock scan...", file=sys.stderr)
    scan_data = scan_stock_opportunities(twse_all)

    print("Computing signal...", file=sys.stderr)
    signal = compute_market_signal(vix_data, cnn_data, institutional_data)

    analysis = generate_expert_analysis(vix_data, cnn_data, institutional_data, signal)

    output = {
        "last_updated": datetime.now(TW_TZ).isoformat(),
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "vix": vix_data,
        "vix_history": vix_history,
        "cnn_fear_greed": cnn_data,
        "institutional": institutional_data,
        "signal": signal,
        "analysis": analysis,
        "drai": drai_data,
        "heatmap": heatmap_data,
        "scan": scan_data,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Done. Signal: {signal['score']:+.1f} ({signal['outlook']})", file=sys.stderr)
    print(json.dumps({"signal": signal["score"], "outlook": signal["outlook"]}))


if __name__ == "__main__":
    main()
