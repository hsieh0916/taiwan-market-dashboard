import requests, urllib3, re, sys
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

r = s.get('https://mis.taifex.com.tw/futures/_nuxt/cd35741.js', timeout=15)
text = r.text

# Find all string literals near VolatilityQuotes
idx = 0
while True:
    pos = text.find('Volatility', idx)
    if pos == -1:
        break
    chunk = text[max(0, pos-200):pos+300]
    # Print as bytes to avoid encoding issues
    try:
        safe = chunk.encode('ascii', errors='replace').decode('ascii')
        print(f'--- pos {pos} ---')
        print(safe)
    except:
        pass
    idx = pos + 1

print('\n\n=== Searching for HTTP endpoints ===')
# Find axios/fetch/http calls
http_patterns = re.findall(r'(?:axios|http|fetch|get|post)\s*[.(]\s*["\']([^"\']{5,100})["\']', text, re.IGNORECASE)
for p in http_patterns[:30]:
    if any(x in p for x in ['api', 'Api', 'API', 'data', 'query', '/']):
        print(' ', repr(p))

print('\n\n=== Searching for /api/ paths ===')
api_paths = re.findall(r'["\`](\/?(?:api|data|query|service)[^"\`\s]{3,80})["\`]', text)
for p in api_paths[:20]:
    print(' ', repr(p))
