"""
Wait longer and capture all WebSocket traffic from TAIFEX VolatilityQuotes page.
"""
import asyncio, re, json

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors'])
        page = await browser.new_page()

        all_in = []
        all_out = []

        def on_ws(ws):
            print(f'WS: {ws.url}')
            ws.on('framereceived', lambda p: all_in.append(str(p)))
            ws.on('framesent', lambda p: all_out.append(str(p)))

        page.on('websocket', on_ws)

        print('Loading page...')
        await page.goto('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=30000)

        # Wait for page to fully initialize and subscribe
        await page.wait_for_timeout(25000)

        print(f'\n=== Outgoing messages ({len(all_out)}) ===')
        for msg in all_out:
            safe = msg.encode('ascii', errors='replace').decode('ascii')
            print(f'  OUT: {safe[:600]}')

        print(f'\n=== Incoming messages ({len(all_in)}) ===')
        for msg in all_in:
            safe = msg.encode('ascii', errors='replace').decode('ascii')
            print(f'  IN: {safe[:600]}')

        # Try to get page content after data loads
        body = await page.inner_text('body')
        # Find numbers in right VIX range
        nums = re.findall(r'\b(\d{1,2}\.\d{2})\b', body)
        vix_candidates = [float(n) for n in set(nums) if 8.0 <= float(n) <= 80.0]
        print(f'\n=== VIX-like numbers on page: {vix_candidates} ===')

        # Get all visible div/span text that looks like a value
        elements = await page.query_selector_all('[class*="value"], [class*="price"], [class*="index"], span, div')
        print('\n=== Element texts with numbers ===')
        seen = set()
        for el in elements[:200]:
            try:
                text = (await el.inner_text()).strip()
                if text and text not in seen and re.match(r'^\d{1,2}\.\d{2}$', text):
                    seen.add(text)
                    cls = await el.get_attribute('class') or ''
                    safe_cls = cls.encode('ascii', errors='replace').decode('ascii')
                    print(f'  [{text}] class={safe_cls[:60]}')
            except:
                pass

        await browser.close()

asyncio.run(main())
