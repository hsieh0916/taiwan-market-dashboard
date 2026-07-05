#!/usr/bin/env python3
"""
One-time backfill for institutional.history.

BFI82U (the TWSE market-wide 三大法人買賣超金額 report) ignores its `date`
param and always returns the latest trading day, so fetch_data.py can only
accumulate one real day at a time going forward (see HANDOFF.md).

T86 (per-stock 法人買賣超股數) and MI_INDEX (per-stock 收盤行情) both honor
`date` and return every listed stock in a single call, so historical days
can be approximated as sum(net_shares_by_category * closing_price) across
all stocks. This is an ESTIMATE — TWSE's real BFI82U figure is buy_amount
minus sell_amount at actual trade prices, not shares * close — but it's
close enough to give the chart a real trend instead of one bar.

Entries this script writes are tagged "estimated": true. The existing
BFI82U-sourced entry for today's date is left untouched.

Usage:
    python scripts/backfill_institutional_history.py [--days 60]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
from fetch_data import _session, OUTPUT_PATH  # noqa: E402  (reuse shared session/config)

T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
MI_INDEX_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
REQUEST_DELAY = 0.4  # seconds between requests, be polite to TWSE


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("+", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch_t86(date_str):
    r = _session.get(T86_URL, params={"response": "json", "selectType": "ALL", "date": date_str}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("stat") != "OK" or not data.get("data"):
        return None

    fields = [f.replace(" ", "").replace("\n", "") for f in data.get("fields", [])]

    def exact_col(name, default):
        try:
            return fields.index(name)
        except ValueError:
            return default

    # Exact field names from a live T86 response (see backfill investigation):
    # 4  外陸資買賣超股數(不含外資自營商)
    # 10 投信買賣超股數
    # 11 自營商買賣超股數   <- combined self-trading + hedge, NOT "...(自行買賣)" / "...(避險)"
    col_foreign = exact_col("外陸資買賣超股數(不含外資自營商)", 4)
    col_trust = exact_col("投信買賣超股數", 10)
    col_dealer = exact_col("自營商買賣超股數", 11)

    out = {}
    for row in data["data"]:
        if len(row) < 3:
            continue
        code = str(row[0]).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue
        f_net = _num(row[col_foreign]) if col_foreign < len(row) else 0
        t_net = _num(row[col_trust]) if col_trust < len(row) else 0
        d_net = _num(row[col_dealer]) if col_dealer < len(row) else 0
        out[code] = {"foreign": f_net or 0, "trust": t_net or 0, "dealer": d_net or 0}
    return out


def fetch_closing_prices(date_str):
    r = _session.get(MI_INDEX_URL, params={"response": "json", "date": date_str, "type": "ALLBUT0999"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    tables = data.get("tables", [])
    price_table = None
    for t in tables:
        if "每日收盤行情" in (t.get("title") or ""):
            price_table = t
            break
    if not price_table:
        return None

    fields = price_table.get("fields", [])
    try:
        code_idx = fields.index("證券代號")
        close_idx = fields.index("收盤價")
    except ValueError:
        return None

    out = {}
    for row in price_table.get("data", []):
        code = str(row[code_idx]).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue
        price = _num(row[close_idx])
        if price is not None and price > 0:
            out[code] = price
    return out


def estimate_day(date_str):
    """Returns {foreign, investment_trust, dealer, total} in NT$, or None if not a trading day."""
    shares = fetch_t86(date_str)
    if not shares:
        return None
    time.sleep(REQUEST_DELAY)
    prices = fetch_closing_prices(date_str)
    if not prices:
        return None

    foreign_val = trust_val = dealer_val = 0.0
    for code, s in shares.items():
        price = prices.get(code)
        if price is None:
            continue
        foreign_val += s["foreign"] * price
        trust_val += s["trust"] * price
        dealer_val += s["dealer"] * price

    return {
        "foreign": round(foreign_val),
        "investment_trust": round(trust_val),
        "dealer": round(dealer_val),
        "total": round(foreign_val + trust_val + dealer_val),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60, help="number of trading days to backfill")
    args = parser.parse_args()

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        market_data = json.load(f)

    history = market_data.get("institutional", {}).get("history", []) or []
    existing_dates = {e["date"] for e in history}

    collected = []
    cursor = datetime.now() - timedelta(days=1)
    scanned = 0
    max_scan = args.days * 2 + 20  # enough calendar days to cover weekends/holidays

    while len(collected) < args.days and scanned < max_scan:
        date_str = cursor.strftime("%Y%m%d")
        scanned += 1
        cursor -= timedelta(days=1)

        if date_str in existing_dates:
            print(f"{date_str}: skip (already real BFI82U data)", file=sys.stderr)
            continue

        try:
            est = estimate_day(date_str)
        except Exception as e:
            print(f"{date_str}: error {e}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
            continue

        if est is None:
            print(f"{date_str}: not a trading day, skip", file=sys.stderr)
            time.sleep(REQUEST_DELAY * 0.5)
            continue

        entry = {"date": date_str, "estimated": True, **est}
        collected.append(entry)
        print(f"{date_str}: foreign={est['foreign']/1e8:+.1f}億 trust={est['investment_trust']/1e8:+.1f}億 "
              f"dealer={est['dealer']/1e8:+.1f}億 total={est['total']/1e8:+.1f}億", file=sys.stderr)
        time.sleep(REQUEST_DELAY)

    merged = history + collected
    merged.sort(key=lambda e: e["date"])
    market_data.setdefault("institutional", {})["history"] = merged

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    print(f"\nBackfilled {len(collected)} trading days. institutional.history now has {len(merged)} entries.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
