import asyncio
from playwright.async_api import async_playwright

async def diagnose():
    async with async_playwright() as p:
        print("Connecting to running Chrome via CDP...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = await context.new_page()
        
        print("Navigating to https://studio.youtube.com/channel/UCTynXOGpihxhmCRdt7iA5wA/videos without resource blocking...")
        await page.goto("https://studio.youtube.com/channel/UCTynXOGpihxhmCRdt7iA5wA/videos", timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        screenshot_path = "/Users/sunildarna/.gemini/antigravity/browser_recordings/diagnose_content_page.png"
        await page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")
        
        # Let's inspect the DOM elements with "Shorts" in their text or tag names
        print("Searching for elements containing 'Shorts'...")
        elements = await page.query_selector_all("//*[contains(text(), 'Shorts') or contains(@label-text, 'Shorts') or contains(@id, 'shorts')]")
        print(f"Found {len(elements)} elements matching the search.")
        for idx, elem in enumerate(elements[:20]):
            try:
                tag_name = await elem.evaluate("el => el.tagName")
                text = await elem.inner_text()
                attrs = await elem.evaluate("el => { return { id: el.id, className: el.className, labelText: el.getAttribute('label-text') }; }")
                print(f"[{idx}] Tag: {tag_name}, Text: {repr(text.strip())}, Attrs: {attrs}")
            except Exception as e:
                print(f"[{idx}] Error evaluating element: {e}")
                
        # Also print all ytcp-text-menu-item elements
        print("\nAll ytcp-text-menu-item elements:")
        menu_items = await page.query_selector_all("ytcp-text-menu-item")
        for idx, item in enumerate(menu_items):
            try:
                text = await item.inner_text()
                label = await item.get_attribute("label-text")
                print(f"[{idx}] Text: {repr(text.strip())}, label-text attr: {label}")
            except Exception as e:
                print(f"[{idx}] Error: {e}")
                
        await page.close()

if __name__ == "__main__":
    asyncio.run(diagnose())
