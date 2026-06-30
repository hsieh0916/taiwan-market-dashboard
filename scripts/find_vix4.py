"""
Connect directly to TAIFEX WebSocket and capture STOMP messages
to find the VIX data topic and format.
"""
import asyncio, re, json

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors'])
        page = await browser.new_page()

        all_ws_messages = []
        ws_ref = []

        def on_ws(ws):
            print(f'WS connected: {ws.url}')
            ws_ref.append(ws)

            def on_frame(payload):
                all_ws_messages.append(payload)
                safe = str(payload).encode('ascii', errors='replace').decode('ascii')
                if len(safe) > 3:
                    print(f'WS IN: {safe[:500]}')

            ws.on('framereceived', on_frame)
            ws.on('framesent', lambda p: print(f'WS OUT: {str(p)[:200]}'))

        page.on('websocket', on_ws)

        print('Loading page...')
        await page.goto('https://mis.taifex.com.tw/futures/VolatilityQuotes/', timeout=30000)

        # Wait for WebSocket to connect and data to flow
        await page.wait_for_timeout(20000)

        print(f'\n=== Total WS messages: {len(all_ws_messages)} ===')
        # Print all messages
        for i, msg in enumerate(all_ws_messages):
            safe = str(msg).encode('ascii', errors='replace').decode('ascii')
            print(f'[{i}] {safe[:600]}')

        await browser.close()

asyncio.run(main())
