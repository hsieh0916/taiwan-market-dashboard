import requests, urllib3, re
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://mis.taifex.com.tw/futures/VolatilityQuotes/'})

# Chunk 4 = 94c18ce.js (shared by all quote pages including VolatilityQuotes)
r = s.get('https://mis.taifex.com.tw/futures/_nuxt/94c18ce.js', timeout=15)
text = r.text
print(f'Chunk 4 (94c18ce.js): {len(text)} bytes')

# Search for subscribe/topic patterns
topics = re.findall(r'["\']([^"\']*(?:/topic|/queue|/app|subscribe)[^"\']{0,100})["\']', text)
print('\n=== STOMP Topics ===')
for t in topics[:30]:
    print(' ', repr(t.encode('ascii','replace').decode('ascii')))

# Search for API URL patterns
api_urls = re.findall(r'["\']([^"\']*(?:api/|/data/|snapshot|init|initial)[^"\']{0,100})["\']', text, re.IGNORECASE)
print('\n=== API/Snapshot URLs ===')
for u in api_urls[:30]:
    print(' ', repr(u.encode('ascii','replace').decode('ascii')))

# Search for axios/http specific patterns
http_calls = re.findall(r'(?:this\.\$http|axios|Vue\.http)\s*\.\s*(?:get|post)\s*\(\s*["\']([^"\']+)["\']', text)
print('\n=== HTTP calls ===')
for h in http_calls[:20]:
    print(' ', repr(h.encode('ascii','replace').decode('ascii')))

# Search ALL strings that look like API paths
all_paths = re.findall(r'["\`](\/?[a-zA-Z][a-zA-Z0-9]*(?:/[a-zA-Z][a-zA-Z0-9]*)+)["\`]', text)
print('\n=== All path-like strings ===')
seen = set()
for p in all_paths:
    if p not in seen and len(p) > 5 and p.count('/') >= 1:
        seen.add(p)
        print(' ', p)
