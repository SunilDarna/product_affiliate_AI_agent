import asyncio
from playwright.async_api import async_playwright

async def click_shorts():
    async with async_playwright() as p:
        print("Connecting to running Chrome via CDP...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = await context.new_page()
        
        print("Navigating to https://studio.youtube.com/channel/UCTynXOGpihxhmCRdt7iA5wA/videos...")
        await page.goto("https://studio.youtube.com/channel/UCTynXOGpihxhmCRdt7iA5wA/videos", timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        # Print elements around the tab bar by finding the text Shorts
        print("Locating 'Shorts' element...")
        try:
            # Let's try locating using Playwright's locator which automatically pierces Shadow DOM
            shorts_locator = page.locator('text="Shorts"')
            count = await shorts_locator.count()
            print(f"Number of 'Shorts' text elements found: {count}")
            
            for i in range(count):
                el = shorts_locator.nth(i)
                tag = await el.evaluate("el => el.tagName")
                parent_tag = await el.evaluate("el => el.parentElement.tagName")
                inner_html = await el.evaluate("el => el.outerHTML")
                print(f"[{i}] Tag: {tag}, Parent: {parent_tag}, HTML: {inner_html[:200]}")
                
            # Let's try clicking the first visible one
            for i in range(count):
                el = shorts_locator.nth(i)
                if await el.is_visible():
                    print(f"Clicking 'Shorts' element at index {i}...")
                    await el.click()
                    break
            
            await page.wait_for_timeout(5000)
            
            screenshot_path = "/Users/sunildarna/.gemini/antigravity/browser_recordings/after_clicking_shorts.png"
            await page.screenshot(path=screenshot_path)
            print(f"Saved screenshot after click to {screenshot_path}")
            
        except Exception as e:
            print(f"Error locating or clicking: {e}")
            
        await page.close()

if __name__ == "__main__":
    asyncio.run(click_shorts())
