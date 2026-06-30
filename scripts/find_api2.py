import requests, urllib3, re
urllib3.disable_warnings()
s = requests.Session()
s.verify = False
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Get the page source and look for all script/link tags and inline JS
resp = s.get('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=15)
text = resp.text

# Find all JS/CSS resources
all_resources = re.findall(r'(?:src|href)="([^"]+)"', text)
print('All resources:')
for r in all_resources:
    if '.js' in r or '.json' in r:
        print(' ', r)

print('\n\nSearching for fetch/axios/ajax calls in page:')
# Look for any XHR/fetch URLs embedded in the page
fetch_calls = re.findall(r'(?:fetch|axios|ajax|url)\s*[:(]\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
for f in fetch_calls[:20]:
    print(' ', f)

# Also look for the main app js
print('\nAll script sources:')
srcs = re.findall(r'<script[^>]+src="([^"]+)"', text)
for src in srcs:
    print(' ', src)
