import requests, urllib3, re
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

r = s.get('https://mis.taifex.com.tw/futures/_nuxt/cd35741.js', timeout=15)
text = r.text

# Find apiBaseUrl value
print('=== apiBaseUrl ===')
matches = re.findall(r'apiBaseUrl["\s:]+["\']([^"\']+)["\']', text)
for m in matches:
    print(' ', repr(m))

# Find apiMockUrl value
print('\n=== apiMockUrl ===')
matches = re.findall(r'apiMockUrl["\s:]+["\']([^"\']+)["\']', text)
for m in matches:
    print(' ', repr(m))

# Find environment/config block
print('\n=== Config block ===')
config = re.findall(r'\{[^{}]*apiBaseUrl[^{}]*\}', text)
for c in config[:3]:
    safe = c.encode('ascii', errors='replace').decode('ascii')
    print(' ', safe[:500])

# Find TaiwanVIXQuotes context
print('\n=== TaiwanVIXQuotes context ===')
idx = text.find('TaiwanVIXQuotes')
if idx >= 0:
    chunk = text[max(0,idx-300):idx+300]
    safe = chunk.encode('ascii', errors='replace').decode('ascii')
    print(safe)

# Try the page-specific chunk for VolatilityQuotes (chunk 113)
print('\n=== Trying chunk 113 (VolatilityQuotes page) ===')
# From the bundle: n.e(113) loads the VolatilityQuotes component
# Check all numbered chunks
for chunk_num in [113, 114, 115, 116, 117]:
    try:
        cr = s.get(f'https://mis.taifex.com.tw/futures/_nuxt/{chunk_num}.js', timeout=8)
        if cr.status_code == 200:
            ct = cr.text
            vix_refs = re.findall(r'["\']([^"\']*(?:VIX|vix|Volatil|volatil|quote|Quote)[^"\']{0,60})["\']', ct)
            api_refs = re.findall(r'["\`]([^"\'`]*(?:api|subscribe|topic|/data)[^"\'`]{0,80})["\`]', ct)
            print(f'\nChunk {chunk_num} ({len(ct)} bytes):')
            for v in vix_refs[:10]:
                print('  VIX:', repr(v))
            for a in api_refs[:10]:
                print('  API:', repr(a))
    except:
        pass
