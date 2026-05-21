import asyncio
from playwright.async_api import async_playwright

async def print_rows():
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
        
        rows = await page.query_selector_all("ytcp-video-row")
        print(f"Found {len(rows)} video rows.")
        
        for idx, row in enumerate(rows[:10]):
            title_elem = await row.query_selector("a#video-title-anchor, .video-title-anchor, #video-title")
            title = await title_elem.inner_text() if title_elem else "Unknown"
            
            date_elem = await row.query_selector("div#date-cell, .cell-body-text.date, td.column-date")
            date_text = await date_elem.inner_text() if date_elem else "No Date Elem"
            
            print(f"Row [{idx}] Title: {repr(title.strip())}")
            print(f"Row [{idx}] Raw Date Text: {repr(date_text)}")
            print("-" * 50)
            
        await page.close()

if __name__ == "__main__":
    asyncio.run(print_rows())
