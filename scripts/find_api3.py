import requests, urllib3, re
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Search the Nuxt bundles for API endpoint patterns
nuxt_files = [
    '/futures/_nuxt/98e2fca.js',
    '/futures/_nuxt/581b4c0.js',
    '/futures/_nuxt/ab9396b.js',
    '/futures/_nuxt/cd35741.js',
]

all_apis = set()
for path in nuxt_files:
    url = 'https://mis.taifex.com.tw' + path
    try:
        r = s.get(url, timeout=15)
        text = r.text
        print(f'\n=== {path} ({len(text)} bytes) ===')
        # Find URL patterns related to VIX / Volatility
        patterns = re.findall(r'["\`]([^"\`]*(?:Volatil|volatil|VIX|vix|Quote|quote)[^"\`]{0,80})["\`]', text)
        for p in patterns[:20]:
            if len(p) > 3:
                print(' ', repr(p))
                all_apis.add(p)
        # Find any /api/ paths
        api_paths = re.findall(r'["\`](/[^"\`]*api[^"\`]{3,60})["\`]', text, re.IGNORECASE)
        for p in api_paths[:15]:
            print('  API path:', repr(p))
    except Exception as e:
        print(f'  Error: {e}')

# Try rtCore
print('\n=== rtCore ===')
try:
    r = s.get('https://mis.taifex.com.tw/futures/rtCore', timeout=10)
    print('Status:', r.status_code, 'Type:', r.headers.get('Content-Type',''))
    print('Body:', repr(r.text[:300]))
except Exception as e:
    print('Error:', e)
