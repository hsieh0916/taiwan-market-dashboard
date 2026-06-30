import asyncio, re

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        ws_messages = []
        page.on('websocket', lambda ws: (
            ws.on('framereceived', lambda payload: ws_messages.append(str(payload))),
            ws.on('framesent', lambda payload: None)
        ))

        await page.goto('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=30000)
        # Wait longer for WebSocket data to arrive and render
        await page.wait_for_timeout(12000)

        # Get full HTML
        html = await page.content()

        # Search HTML for VIX-like numbers (10-50 range with decimals)
        print('=== VIX-like numbers in HTML ===')
        numbers = re.findall(r'\b(\d{1,2}\.\d{2})\b', html)
        for n in set(numbers):
            val = float(n)
            if 8 <= val <= 60:
                print(f'  {n}')

        # Print WebSocket messages
        print(f'\n=== WebSocket messages ({len(ws_messages)} total) ===')
        for msg in ws_messages[:10]:
            safe = str(msg).encode('ascii', errors='replace').decode('ascii')
            print(f'  {safe[:300]}')

        # Get all table cells content
        print('\n=== Table cells ===')
        cells = await page.query_selector_all('td, th')
        for cell in cells[:50]:
            text = (await cell.inner_text()).strip()
            if text:
                safe = text.encode('ascii', errors='replace').decode('ascii')
                print(f'  [{safe}]')

        await browser.close()

asyncio.run(main())
