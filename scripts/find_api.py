import requests, urllib3, re, json
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Step 1: Get the SPA page and find JS bundle URLs
resp = s.get('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=15)
scripts = re.findall(r'src="(/futures/[^"]+\.js)"', resp.text)
print('JS bundles:')
for sc in scripts[:8]:
    print(' ', sc)

# Step 2: Fetch each JS bundle and search for API patterns
api_patterns = []
for path in scripts[:8]:
    url = 'https://mis.taifex.com.tw' + path
    try:
        r = s.get(url, timeout=10)
        # Search for API endpoint patterns
        matches = re.findall(r'["\']([^"\']*(?:api|Api|API|vix|VIX|volatil|Volatil)[^"\']{3,60})["\']', r.text)
        for m in matches:
            if '/' in m and m not in api_patterns:
                api_patterns.append(m)
    except Exception as e:
        print(f'  Error fetching {path}: {e}')

print('\nAPI patterns found:')
for p in api_patterns[:30]:
    print(' ', p)
