import requests, urllib3, re, json
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://mis.taifex.com.tw/futures/VolatilityQuotes/'})

# Read the 98e2fca.js (manifest / small file) to find chunk mappings
r = s.get('https://mis.taifex.com.tw/futures/_nuxt/98e2fca.js', timeout=10)
text = r.text
safe = text.encode('ascii', errors='replace').decode('ascii')
print('=== Manifest (98e2fca.js) ===')
print(safe[:2000])

# Search ab9396b.js for STOMP/subscribe patterns
print('\n=== Searching ab9396b for subscribe/topic/stomp patterns ===')
r2 = s.get('https://mis.taifex.com.tw/futures/_nuxt/ab9396b.js', timeout=15)
text2 = r2.text
stomp_patterns = re.findall(r'["\']([^"\']*(?:subscribe|topic|stomp|STOMP|/VIX|/Volatil|/quote)[^"\']{0,80})["\']', text2, re.IGNORECASE)
for p in stomp_patterns[:30]:
    safe_p = p.encode('ascii', errors='replace').decode('ascii')
    print(' ', repr(safe_p))

# Search for API initial data load (HTTP GET before websocket)
print('\n=== HTTP GET patterns in ab9396b ===')
get_patterns = re.findall(r'(?:get|GET)\s*[,(]\s*["\']([^"\']+/[^"\']+)["\']', text2)
for p in get_patterns[:20]:
    safe_p = p.encode('ascii', errors='replace').decode('ascii')
    print(' ', safe_p)

# Try SockJS info endpoint
print('\n=== SockJS info endpoint ===')
for url in [
    'https://mis.taifex.com.tw/futures/rtCore/info',
    'https://mis.taifex.com.tw/futures/rtCore/websocket',
]:
    try:
        r3 = s.get(url, timeout=8)
        body = r3.text[:300].encode('ascii', errors='replace').decode('ascii')
        print(f'[{r3.status_code}] {url}: {body}')
    except Exception as e:
        print(f'ERROR {url}: {e}')
