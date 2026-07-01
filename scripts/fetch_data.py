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


def fetch_vix_data():
    """Fetch VIX, VIXTWN, Taiwan OTC and US major index data from Yahoo Finance."""
    tickers = {
        "vix":    "^VIX",
        "vix9d":  "^VIX9D",
        "vix3m":  "^VIX3M",
        "vix6m":  "^VIX6M",
        "twii":   "^TWII",
        "tpex":   "^TWO",    # 台灣櫃買指數 (GreTai OTC)
        "sp500":  "^GSPC",   # 標普500
        "nasdaq": "^IXIC",   # 那斯達克綜合
        "dji":    "^DJI",    # 道瓊工業
    }

    result = {}
    history = {}

    for key, symbol in tickers.items():
        try:
            ticker = yf.Ticker(symbol, session=_session)
            hist = ticker.history(period="60d", interval="1d")

            if not hist.empty:
                result[key] = {
                    "symbol": symbol,
                    "current": round(float(hist["Close"].iloc[-1]), 2),
                    "prev": round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else None,
                    "change": round(float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else 0,
                    "change_pct": round(
                        (float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[-2])) / float(hist["Close"].iloc[-2]) * 100, 2
                    ) if len(hist) > 1 else 0,
                    "high_52w": round(float(hist["Close"].max()), 2),
                    "low_52w": round(float(hist["Close"].min()), 2),
                }
                history[key] = {
                    "dates": [str(d.date()) for d in hist.index],
                    "closes": [round(float(v), 2) for v in hist["Close"].tolist()],
                }
            else:
                result[key] = {"symbol": symbol, "current": None, "error": "no data"}
        except Exception as e:
            result[key] = {"symbol": symbol, "current": None, "error": str(e)}
            print(f"Warning: failed to fetch {symbol}: {e}", file=sys.stderr)

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
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MarketDashboard/1.0)",
        "Referer": "https://www.cnn.com/",
    }
    try:
        resp = _session.get(url, headers={"Referer": "https://www.cnn.com/"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        fg = data.get("fear_and_greed", {})
        historical = data.get("fear_and_greed_historical", {}).get("data", [])

        # Trim historical to last 60 days
        hist_dates = [item["x"] for item in historical[-60:]]
        hist_values = [round(item["y"], 1) for item in historical[-60:]]

        return {
            "current": round(fg.get("score", 0), 1),
            "rating": fg.get("rating", "unknown"),
            "prev_close": round(fg.get("previous_close", 0), 1),
            "prev_1week": round(fg.get("previous_1_week", 0), 1),
            "prev_1month": round(fg.get("previous_1_month", 0), 1),
            "prev_1year": round(fg.get("previous_1_year", 0), 1),
            "history_dates": hist_dates,
            "history_values": hist_values,
        }
    except Exception as e:
        print(f"Warning: failed to fetch CNN F&G: {e}", file=sys.stderr)
        return {"current": None, "rating": "unknown", "error": str(e)}


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
    """Fetch last 20 trading days of institutional data."""
    from datetime import date, timedelta

    results = []
    today = date.today()
    checked = 0
    day = today

    while len(results) < 20 and checked < 60:
        checked += 1
        if day.weekday() >= 5:
            day -= timedelta(days=1)
            continue

        date_str = day.strftime("%Y%m%d")
        url = "https://www.twse.com.tw/fund/BFI82U"
        params = {"response": "json", "type": "day", "dayDate": date_str}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.twse.com.tw/"}

        try:
            resp = _session.get(url, params=params, headers={"Referer": "https://www.twse.com.tw/"}, timeout=10)
            data = resp.json()
            rows = data.get("data", [])
            if rows:
                entry = {"date": date_str, "foreign": 0, "investment_trust": 0, "dealer": 0}

                def parse_num(s):
                    try:
                        return int(str(s).replace(",", "").replace("+", ""))
                    except Exception:
                        return 0

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
        except Exception:
            pass

        day -= timedelta(days=1)

    results.reverse()
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


def main():
    print("Fetching VIX data...", file=sys.stderr)
    vix_data, vix_history = fetch_vix_data()

    print("Fetching CNN Fear & Greed...", file=sys.stderr)
    cnn_data = fetch_cnn_fear_greed()

    print("Fetching TWSE institutional data...", file=sys.stderr)
    institutional_data = fetch_twse_institutional()

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
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Done. Signal: {signal['score']:+.1f} ({signal['outlook']})", file=sys.stderr)
    print(json.dumps({"signal": signal["score"], "outlook": signal["outlook"]}))


if __name__ == "__main__":
    main()
