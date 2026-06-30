"""
Intercept network requests from TAIFEX MIS VolatilityQuotes page
to discover the actual data source (WebSocket topic or REST endpoint).
Run this locally to inspect what the page fetches.
"""
import asyncio, sys

async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Install: pip install playwright && playwright install chromium")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        ws_messages = []
        http_responses = []

        # Capture WebSocket frames
        page.on('websocket', lambda ws: ws.on('framereceived',
            lambda payload: ws_messages.append(str(payload)[:300])))

        # Capture HTTP responses
        async def on_response(response):
            url = response.url
            if any(x in url.lower() for x in ['api', 'vix', 'volatil', 'quote', 'data']):
                try:
                    body = await response.text()
                    http_responses.append((response.status, url, body[:200]))
                except:
                    pass
        page.on('response', on_response)

        print('Opening page...')
        await page.goto('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=30000)
        await page.wait_for_timeout(8000)

        # Try to find VIX value on page
        print('\n=== Page title ===')
        print(await page.title())

        print('\n=== Looking for VIX value in page ===')
        # Try common selectors
        selectors = ['td', '.vix', '[class*="vix"]', '[class*="VIX"]', 'table td']
        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for el in elements[:20]:
                    text = (await el.inner_text()).strip()
                    if text and any(c.isdigit() for c in text) and '.' in text:
                        try:
                            val = float(text.replace(',', ''))
                            if 5 <= val <= 80:  # VIX range
                                print(f'  {sel}: {text}')
                        except:
                            pass
            except:
                pass

        print('\n=== HTTP Responses (API/data related) ===')
        for status, url, body in http_responses[:20]:
            print(f'  [{status}] {url}')
            print(f'    {body[:100]}')

        print('\n=== WebSocket Messages (first 5) ===')
        for msg in ws_messages[:5]:
            print(f'  {msg[:200]}')

        await browser.close()

asyncio.run(main())
