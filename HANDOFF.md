# Taiwan Market Dashboard — Engineering Handoff

**Live site**: https://hsieh0916.github.io/taiwan-market-dashboard/  
**Repo**: https://github.com/hsieh0916/taiwan-market-dashboard  
**Last updated**: 2026-07-05  

---

## What this is

A static GitHub Pages dashboard showing Taiwan (TWSE/TPEX) and US market data. There is **no server** — all data is fetched by a GitHub Actions cron job that writes one JSON file (`data/market_data.json`). The front end reads that file at load time.

---

## Architecture

```
GitHub Actions (fetch_data.yml)
  └─ scripts/fetch_data.py   → writes data/market_data.json
                                       │
                                       ▼
GitHub Actions (deploy_pages.yml)
  └─ deploys the whole repo as a static site
                                       │
                                       ▼
index.html + js/app.js + css/style.css
  └─ fetch('data/market_data.json') on load, render in place
```

**No build step. No node_modules. No framework.** Vanilla JS + Chart.js (CDN).

---

## File map

| File | Purpose |
|---|---|
| `scripts/fetch_data.py` | All data fetching logic (1 742 lines). One `main()` writes the JSON. |
| `scripts/backfill_institutional_history.py` | One-time/rerunnable backfill for `institutional.history` via T86 + MI_INDEX (BFI82U has no historical query). Run manually, not part of the cron. |
| `data/market_data.json` | Output — committed by GitHub Actions, never edited by hand. |
| `index.html` | All HTML structure (~530 lines). Cache-bust version: `v=20260705c`. |
| `js/app.js` | All rendering logic (~1 030 lines). One `loadData()` entry point. |
| `css/style.css` | All styles (~800 lines). CSS variables for light/dark themes. |
| `.github/workflows/fetch_data.yml` | Cron schedule + fetch job. |
| `.github/workflows/deploy_pages.yml` | Pages deploy (triggers on non-data pushes to main). |
| `requirements.txt` | Python deps for the fetch script. |

---

## Cron schedule (all UTC)

| Cron | UTC | Taiwan (TST = UTC+8) | Purpose |
|---|---|---|---|
| `7,37 1-9 * * 1-5` | Mon–Fri 01:07–09:37 | Mon–Fri 09:07–17:37 | Taiwan market hours, every 30 min |
| `7 22 * * 0-5` | Sun–Fri 22:07 | Mon–Sat 06:07 | Pre-Taiwan-open; also captures prior-night US close (US closes ~20:00–21:00 UTC) |
| `7 10 * * 5` | Fri 10:07 | Fri 18:07 | Friday Taiwan post-close (institutional data) |

**Key fact**: US markets close ~20:00 UTC (EDT) or ~21:00 UTC (EST). The `7 22 * * 0-5` run fires 1–2 hours after US close Mon–Fri, and also fires Saturday 06:07 TST to capture Friday's final US prices for weekend viewers.

**Why `:07`/`:37` and not `:00`/`:30`**: GitHub's own docs warn that the scheduler is most congested — and most likely to delay or silently drop a run — exactly on the hour/half-hour. Confirmed empirically here: from 2026-07-01 (when the every-30-min cron went live) through 2026-07-03, only 4 of ~36 expected `*/30 1-9 * * 1-5` runs actually fired, two of them over an hour late. Offsetting a few minutes past the boundary is GitHub's recommended mitigation. If misses continue after this change, the next step is an external pinger (e.g. cron-job.org hitting the GitHub API to trigger `workflow_dispatch`) instead of relying on GitHub's internal `schedule` event.

---

## Data sources in `fetch_data.py`

| Function | Source | Data |
|---|---|---|
| `fetch_vix_data()` | yfinance | VIX, VIX9D, VIX3M, VIX6M, S&P500, NASDAQ, DJI, SOX, Nikkei, KOSPI, TWII. Adds `data_date` field (last yfinance date) to each entry. |
| `fetch_tpex_index()` | TPEx HTML scrape | TPEX index with history accumulation |
| `fetch_vixtwn_from_taifex()` | TAIFEX WebSocket + REST | Taiwan VIX (real-time during market hours) |
| `fetch_cnn_fear_greed()` | CNN API | Fear & Greed index |
| `fetch_twse_institutional()` | TWSE BFI82U API | 三大法人 (foreign/trust/dealer net buy/sell) daily totals |
| `fetch_twse_institutional_history()` | **JSON accumulation** | 30-day history — appended each run; **TWSE API ignores date param so history must be built this way** |
| `_fetch_twse_all_stocks()` | TWSE STOCK_DAY_ALL | All TWSE stocks: code, name, close, change_pct, vol_value |
| `fetch_heatmap_data()` | TWSE MIS real-time API + fallback to STOCK_DAY_ALL | Heatmap quote data |
| `scan_stock_opportunities(twse_raw)` | yfinance batch + TWSE T86 + TWSE BWIBBU_d | Post-market stock screener (see section below) |
| `fetch_drai_holdings()` | DRAI website scrape | ETF institutional holdings |
| `compute_market_signal()` | Derived | Bull/Bear signal from VIX + CNN + institutional |

---

## JSON structure (`data/market_data.json`)

```json
{
  "last_updated": "2026-07-05T00:43:29+08:00",
  "last_updated_utc": "...",
  "vix": {
    "vix":    { "symbol", "current", "prev", "change", "change_pct", "data_date", ... },
    "sp500":  { ..., "ma20", "ma60", "ma240", "ma20_diff_pct", "data_date" },
    "twii":   { ... },
    "tpex":   { ... },
    "vixtwn": { ... }
    // + vix9d, vix3m, vix6m, nasdaq, dji, sox, nikkei, kospi
  },
  "vix_history": { "sp500": { "dates": [...], "closes": [...] }, ... },
  "cnn_fear_greed": { "value", "label", "prev_close", "one_week_ago", ... },
  "institutional": {
    "date", "foreign", "investment_trust", "dealer", "total",
    "history": [ { "date", "foreign", "investment_trust", "dealer", "total" }, ... ]
    // history is accumulated across runs, rolling 60-day window (fetch_data.py caps at [-60:]).
    // Days backfilled by scripts/backfill_institutional_history.py carry "estimated": true
    // (computed as net_shares(T86) * closing_price(MI_INDEX), since BFI82U itself has no
    // historical query — see "Known state" below). Today's entry from the normal cron run
    // is always the real BFI82U figure and has no "estimated" key.
  },
  "heatmap": { "as_of", "twse": [...], "tpex": [...] },
  "scan": {
    "as_of": "2026/07/05 00:43",
    "is_cached": false,           // true when today returned 0 candidates
    "candidates": [               // top 20, sorted by total_score desc
      {
        "code", "name", "close", "change_pct", "vol_b",
        "tech_score", "chip_score", "val_score", "total_score",
        "signals": ["多頭排列", "RSI54", "外資↑", ...],
        "pe", "div_yield"
      }
    ]
  },
  "signal": { "label", "score", "factors": [...] },
  "analysis": { ... },
  "drai": { "as_of", "holdings": [...] }
}
```

---

## Stock screener (`scan_stock_opportunities`)

Scores each stock 0–100:

| Component | Max | Signals |
|---|---|---|
| Technical | 50 | MA20 > MA60 (+8), RSI 50–70 (+10), MACD crossover (+4), volume surge ≥1.5× (+8), 20d momentum (+3–10) |
| Chip | 30 | Foreign net buy (+8+4), trust net buy (+8+4), both buying (+6) |
| Valuation | 20 | P/E ≤15 (+10), P/E 15–25 (+5), div yield ≥4% (+10), ≥2% (+5) |

**Universe**: top 120 TWSE stocks by 成交金額 (min close ≥ NT$20, vol_value ≥ 2億).  
**Filter**: `total_score ≥ 35 AND tech_score ≥ 15`.  
**Fallback**: if 0 candidates this run, reads last non-empty scan from saved JSON and returns it with `is_cached: true`.

Data sources used by scanner:
- `twse_raw` (passed in from `_fetch_twse_all_stocks()`)
- `yfinance.download(tickers, period="90d")` — batch `.TW` suffix tickers
- `_fetch_twse_inst_per_stock()` → TWSE T86 API (field names have newlines; parsed dynamically, fallback col indices 4/10/17)
- `_fetch_twse_valuation()` → TWSE BWIBBU_d API

---

## Taiwan color convention

**Rises = Red (`#f44336`), Falls = Green (`#00e676`)** — opposite of Western convention. This is intentional throughout CSS and JS.

---

## Deploy flow

1. **Data commit** (`chore: update market data`) pushed by `fetch_data.yml` → triggers `deploy_pages.yml` via `gh workflow run`
2. **Code commit** pushed to `main` (non-data files) → triggers `deploy_pages.yml` automatically via `on: push`
3. `deploy_pages.yml` uploads the entire repo as a Pages artifact and deploys it

**Intermittent issue**: GitHub Pages CDN occasionally returns `"Deployment failed, try again later"` on the first deploy attempt. Re-running `deploy_pages.yml` manually always succeeds. This is a GitHub infrastructure issue, not a code issue.

**To manually trigger a data refresh**:
```bash
gh workflow run fetch_data.yml --ref main
```

**To manually trigger a Pages redeploy**:
```bash
gh workflow run deploy_pages.yml --ref main
```

---

## Known state / known gaps (as of 2026-07-11)

| Item | Status |
|---|---|
| `institutional.history` | 28 days as of 2026-07-11 (2026-06-01 → 2026-07-09, missing 07-10: TWSE returned no T86 data for that date, not a WAF block). Rolling window is 60 days (`fetch_data.py` caps at `[-60:]`); grows 1 real entry per trading day going forward. **2026-07-10 incident**: a single BFI82U fetch got blocked by TWSE's WAF mid-run; `fetch_twse_institutional()`'s except branch returned an error dict with no `history` key, so the *next* successful run read "no saved history" and reset the whole 28-day series down to 1 entry. Fixed — the except branch now still calls `fetch_twse_institutional_history(today_entry=None)` to carry the existing history forward on a failed fetch. The lost 28 days were recovered from git history (commit `6c6cd41`), not re-scraped. |
| `scan` (weekend) | Returns Friday's data with `is_cached: true`. Works as designed. |
| `vix.sp500.data_date` | Shows `2026-07-02` — correct, US markets closed Jul 3–4 (Independence Day + observed). |
| Frontend "資料截至 MM/DD" badge | Shows in US indices section header when `data_date ≠ today (TST)`. |
| `scan_stock_opportunities` yfinance | Uses `.TW` suffix. Returns `pd.MultiIndex` for multi-ticker downloads; handled via `df.xs("Close", axis=1, level=0)`. |

---

## How to work on this locally

```bash
# Python deps
pip install -r requirements.txt

# Run the fetch script manually (writes data/market_data.json)
python scripts/fetch_data.py

# Serve the site locally (required — fetch() blocked on file://)
python -m http.server 8080
# then open http://localhost:8080
```

The front end will automatically fall back to the absolute GitHub Pages URL
(`DATA_URL_ABS`) if the relative fetch fails, so opening via `file://` will
show live data from the deployed site.

---

## Things to be careful about

1. **Never edit `data/market_data.json` by hand** — it is overwritten on every fetch run.
2. **Cache-bust version** in `index.html`: update `v=YYYYMMDD[x]` in the two `<link>` / `<script>` tags whenever changing `app.js` or `style.css`.
3. **TWSE BFI82U date param is ignored** — the API always returns today's institutional data regardless of the `date` param. History is built by JSON accumulation only.
4. **Push conflicts**: GitHub Actions commits data on its own schedule. Always `git pull --rebase origin main` before pushing.
5. **`scripts/find_api*.py`** — these are exploratory/throwaway scripts from early API discovery. They are not part of the application.
