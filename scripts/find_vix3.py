import asyncio, re

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors'])
        page = await browser.new_page()

        captured_ws = []

        def on_ws(ws):
            print(f'WS connected: {ws.url}')
            ws.on('framereceived', lambda payload: captured_ws.append(payload))

        page.on('websocket', on_ws)

        print('Loading page...')
        await page.goto('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=30000)
        await page.wait_for_timeout(15000)

        # Screenshot
        await page.screenshot(path='scripts/vix_page.png', full_page=False)
        print('Screenshot saved to scripts/vix_page.png')

        # Get all text
        body_text = await page.inner_text('body')
        safe_text = body_text.encode('ascii', errors='replace').decode('ascii')
        print(f'\n=== Page text (first 2000 chars) ===')
        print(safe_text[:2000])

        print(f'\n=== WebSocket messages ({len(captured_ws)}) ===')
        for msg in captured_ws[:5]:
            safe = str(msg).encode('ascii', errors='replace').decode('ascii')
            print(f'  {safe[:400]}')

        # Try to find numbers in visible text
        print('\n=== Numbers that look like VIX (8-80) ===')
        nums = re.findall(r'\b(\d{1,2}\.\d{2})\b', safe_text)
        for n in set(nums):
            if 8.0 <= float(n) <= 80.0:
                print(f'  {n}')

        await browser.close()

asyncio.run(main())
