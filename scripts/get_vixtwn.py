"""
Fetch VIXTWN from TAIFEX mis.taifex.com.tw/futures/VolatilityQuotes/
Handles the disclaimer modal, then captures WebSocket data.
"""
import asyncio, re, json

async def fetch_vixtwn():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--ignore-certificate-errors', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            locale='zh-TW',
        )
        page = await context.new_page()

        ws_data = []
        def on_ws(ws):
            ws.on('framereceived', lambda p: ws_data.append(str(p)))

        page.on('websocket', on_ws)

        await page.goto('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=30000)
        await page.wait_for_timeout(2000)

        # Scroll to bottom to reveal the agree buttons
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(1000)

        # Screenshot before click
        await page.screenshot(path='scripts/disclaimer.png', full_page=True)

        # Click the orange agree button (class="btn" without "secondary")
        # Buttons: [0]=navbar, [1]=close, [2]=同意(btn), [3]=不同意(btn-secondary)
        buttons = await page.query_selector_all('button')
        print(f'Found {len(buttons)} buttons')
        for i, btn in enumerate(buttons):
            cls = await btn.get_attribute('class') or ''
            txt = (await btn.inner_text()).strip()
            txt_safe = txt.encode('ascii', errors='replace').decode('ascii')
            print(f'  [{i}] "{txt_safe}" class="{cls}"')

        # Click button index 2 = the primary/orange agree button
        if len(buttons) >= 3:
            agree_btn = buttons[2]
            await agree_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await agree_btn.click()
            print('Clicked agree button!')

        # Wait for VolatilityQuotes page to fully load with WebSocket data
        await page.wait_for_timeout(20000)

        # Screenshot after disclaimer
        await page.screenshot(path='scripts/vix_data.png', full_page=False)
        print('Screenshot saved: scripts/vix_data.png')

        # Extract VIX value from page
        body_text = await page.inner_text('body')

        # Search for VIXTWN value — look for numbers in 8-80 range with 2 decimals
        nums = re.findall(r'\b(\d{1,2}\.\d{2})\b', body_text)
        vix_candidates = sorted(set(float(n) for n in nums if 8.0 <= float(n) <= 80.0))
        print(f'VIX candidates: {vix_candidates}')

        # Also look for any element containing the VIXTWN value
        print('\nAll XX.XX values on page:')
        for sel in ['td', 'span', 'div']:
            els = await page.query_selector_all(sel)
            for el in els[:500]:
                try:
                    text = (await el.inner_text()).strip()
                    if re.match(r'^\d{1,2}\.\d{2}$', text):
                        cls = await el.get_attribute('class') or ''
                        print(f'  {sel}.{cls[:30]} = {text}')
                except:
                    pass

        # WebSocket messages
        print(f'\nWS messages received: {len(ws_data)}')
        for msg in ws_data[:15]:
            safe = msg.encode('ascii', errors='replace').decode('ascii')
            print(f'  {safe[:500]}')

        await browser.close()
        return vix_candidates[0] if vix_candidates else None

if __name__ == '__main__':
    result = asyncio.run(fetch_vixtwn())
    print(f'\nVIXTWN = {result}')
