# 台股市場情緒儀表板 🇹🇼

**Taiwan Market Intelligence Dashboard**

結合台灣VIX（VIXTWN）、美股VIX期限結構、CNN恐懼貪婪指數及三大法人動向，推估台灣股市短中期走勢的專業儀表板。

🌐 **Live Site**: https://YOUR_GITHUB_USERNAME.github.io/taiwan-market-dashboard

---

## 功能特色

| 指標 | 說明 |
|------|------|
| 🌡️ VIXTWN | 台灣波動率指數，衡量本土市場恐慌程度 |
| 🇺🇸 美股VIX | S&P500 VIX，反映全球風險情緒 |
| 📊 VIX期限結構 | VIX9D/VIX/VIX3M/VIX6M 曲線形狀分析 |
| 📡 CNN恐懼貪婪 | 美股綜合情緒指數 |
| 🏦 三大法人 | 外資、投信、自營商買賣超統計 |
| 🔬 綜合信號 | 加權評分 -100 至 +100，產出做多/做空建議 |

## 信號計算邏輯

```
綜合信號 = 
  VIXTWN信號    × 30%  +
  美股VIX信號   × 15%  +
  VIX期限結構   × 15%  +
  CNN恐懼貪婪   × 15%  +
  三大法人動向  × 25%
```

| 分數範圍 | 判斷 |
|---------|------|
| +50 ~ +100 | 強力做多 (STRONG BUY) |
| +20 ~ +50  | 偏多 (BUY) |
| -20 ~ +20  | 中性觀望 (NEUTRAL) |
| -50 ~ -20  | 偏空 (SELL) |
| -100 ~ -50 | 強力做空 (STRONG SELL) |

## 資料來源

- **Yahoo Finance** — VIXTWN、VIX、VIX9D、VIX3M、VIX6M、加權指數
- **CNN Business** — Fear & Greed Index
- **台灣證券交易所 (TWSE)** — 三大法人買賣超

## 部署方式

### 1. Fork 或 Clone 此 Repo

```bash
git clone https://github.com/YOUR_USERNAME/taiwan-market-dashboard.git
```

### 2. 啟用 GitHub Pages

Settings → Pages → Source: `main` branch, `/ (root)`

### 3. 設定 GitHub Actions 自動更新

Actions 頁面確認 workflow 有執行權限：  
Settings → Actions → General → Allow all actions ✓

Workflow 每小時在台灣市場交易時段（UTC 01:00–09:00）自動執行，抓取最新數據並 commit 到 `data/market_data.json`。

### 4. 手動觸發 (選用)

Actions → Fetch Market Data → Run workflow

### 本機測試

```bash
pip install yfinance requests
python scripts/fetch_data.py
# 開啟 index.html 於瀏覽器
```

## 免責聲明

> ⚠️ 本儀表板僅供參考，不構成任何投資建議。股市投資存在風險，請獨立判斷並自負盈虧。

---

*數據每小時自動更新 · Built with GitHub Pages + Actions*
