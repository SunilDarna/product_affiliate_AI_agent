import asyncio
from playwright.async_api import async_playwright

async def print_html():
    async with async_playwright() as p:
        print("Connecting to running Chrome...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = await context.new_page()
        
        print("Navigating to https://studio.youtube.com/channel/UCTynXOGpihxhmCRdt7iA5wA/videos...")
        await page.goto("https://studio.youtube.com/channel/UCTynXOGpihxhmCRdt7iA5wA/videos", timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        # Click Shorts tab
        shorts_locator = page.locator('text="Shorts"')
        count = await shorts_locator.count()
        for i in range(count):
            el = shorts_locator.nth(i)
            if await el.is_visible():
                await el.click()
                break
        await page.wait_for_timeout(5000)
        
        row = await page.query_selector("ytcp-video-row")
        if row:
            html = await row.evaluate("el => el.outerHTML")
            print("OUTER HTML OF YTCP-VIDEO-ROW:")
            print(html[:1500])
            print("...")
            print(html[-1500:])
        else:
            print("No ytcp-video-row found!")
            
        await page.close()

if __name__ == "__main__":
    asyncio.run(print_html())
