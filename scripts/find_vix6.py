"""
Click the disclaimer and capture VIXTWN data from TAIFEX VolatilityQuotes page.
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

        print('Loading disclaimer page...')
        await page.goto('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=30000)
        await page.wait_for_timeout(3000)

        # Take screenshot before clicking
        await page.screenshot(path='scripts/before_click.png')
        print('Screenshot: before_click.png')

        # Find and click the agree/confirm button (orange button)
        # Try multiple selectors for the disclaimer button
        clicked = False
        for selector in [
            'button.btn-primary',
            'button:has-text("同意")',
            'button:has-text("確認")',
            'button:has-text("我已")',
            '.btn-primary',
            'button[type="button"]:first-of-type',
            'button',
        ]:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    text = await btn.inner_text()
                    safe = text.encode('ascii', errors='replace').decode('ascii')
                    print(f'Found button [{safe.strip()}] with selector: {selector}')
                    await btn.click()
                    clicked = True
                    print(f'Clicked! Waiting for data...')
                    break
            except Exception as e:
                pass

        if not clicked:
            # Try clicking all buttons and see
            buttons = await page.query_selector_all('button')
            print(f'Found {len(buttons)} buttons:')
            for i, b in enumerate(buttons):
                try:
                    text = await b.inner_text()
                    safe = text.encode('ascii', errors='replace').decode('ascii')
                    cls = await b.get_attribute('class') or ''
                    print(f'  [{i}] "{safe.strip()}" class="{cls}"')
                except:
                    pass

        # Wait for data to load after clicking
        await page.wait_for_timeout(15000)

        # Screenshot after click
        await page.screenshot(path='scripts/after_click.png')
        print('Screenshot: after_click.png')

        # Get page text
        body = await page.inner_text('body')
        nums = re.findall(r'\b(\d{1,2}\.\d{2})\b', body)
        vix_candidates = [float(n) for n in set(nums) if 8.0 <= float(n) <= 80.0]
        print(f'\n=== VIX-like numbers: {sorted(vix_candidates)} ===')

        # All elements with decimal numbers
        print('\n=== Elements with XX.XX numbers ===')
        seen = set()
        for sel in ['td', 'span', 'div', 'p']:
            elements = await page.query_selector_all(sel)
            for el in elements[:500]:
                try:
                    text = (await el.inner_text()).strip()
                    if re.match(r'^\d{1,2}\.\d{2}$', text) and text not in seen:
                        seen.add(text)
                        cls = await el.get_attribute('class') or ''
                        safe_cls = cls.encode('ascii', errors='replace').decode('ascii')
                        print(f'  {sel}[{safe_cls[:40]}] = {text}')
                except:
                    pass

        print(f'\n=== WS OUT ({len(all_out)}) ===')
        for msg in all_out:
            safe = msg.encode('ascii', errors='replace').decode('ascii')
            print(f'  {safe[:400]}')

        print(f'\n=== WS IN ({len(all_in)}) ===')
        for msg in all_in[:10]:
            safe = msg.encode('ascii', errors='replace').decode('ascii')
            print(f'  {safe[:600]}')

        await browser.close()

asyncio.run(main())
