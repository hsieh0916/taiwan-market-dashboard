import requests, urllib3, json
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://mis.taifex.com.tw/futures/VolatilityQuotes/',
    'Origin': 'https://mis.taifex.com.tw',
    'Accept': 'application/json, text/plain, */*',
})

base = 'https://mis.taifex.com.tw/futures/api/'

endpoints = [
    'VolatilityQuotes',
    'VolatilityQuotes?SortColumn=&AscDesc=A',
    'TaiwanVIXQuotes',
    'getVolatilityQuotes',
    'getVIX',
    'MarketQuotes/VolatilityQuotes',
    'quotes/VolatilityQuotes',
]

for ep in endpoints:
    url = base + ep
    try:
        r = s.get(url, timeout=10)
        body = r.text[:300].encode('ascii', errors='replace').decode('ascii')
        print(f'[{r.status_code}] {url}')
        print(f'  Type: {r.headers.get("Content-Type","")}')
        print(f'  Body: {body}')
        print()
    except Exception as e:
        print(f'ERROR {url}: {e}')
