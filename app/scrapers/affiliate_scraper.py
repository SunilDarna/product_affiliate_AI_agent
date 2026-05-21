import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import random

# Estimated commission rates by category (Amazon India Associates Average)
COMMISSION_RATES = {
    "electronics": 0.04,
    "accessories": 0.09,
    "appliances": 0.05,
    "fashion": 0.09,
    "default": 0.05
}

# Randomized user agents — same pool as ShortsAutomatorAIAgent local scraper
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# Randomized viewports to mimic real desktop browsers
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
]

def get_local_headers() -> dict:
    """Returns randomized browser headers to mimic a real user — mirrors ShortsAutomatorAIAgent."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9,en-US;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

def guess_category(product_title):
    title = product_title.lower()
    if any(x in title for x in ["watch", "earbuds", "phone", "laptop", "speaker", "headphones", "tablet"]):
        return "electronics"
    elif any(x in title for x in ["cover", "case", "cable", "charger", "stand", "mount"]):
        return "accessories"
    elif any(x in title for x in ["fryer", "blender", "mixer", "oven", "cooker", "iron"]):
        return "appliances"
    elif any(x in title for x in ["shirt", "shoe", "bag", "dress", "kurti", "saree"]):
        return "fashion"
    return "default"

async def search_amazon(query):
    async with async_playwright() as p:
        headers = get_local_headers()
        viewport = random.choice(VIEWPORTS)

        # Launch with stealth settings — randomized UA/viewport to defeat bot fingerprinting
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # Key stealth arg
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            user_agent=headers["User-Agent"],
            viewport=viewport,
            extra_http_headers={
                "Accept-Language": headers["Accept-Language"],
                "Accept-Encoding": headers["Accept-Encoding"],
            },
            locale="en-IN",
        )

        # Mask navigator.webdriver to prevent Playwright detection
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = await context.new_page()

        # Block images/media/fonts to speed up loading — keep HTML/CSS/JS
        await page.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font"]
            else route.continue_()
        )

        url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}&ref=nb_sb_noss"

        try:
            print(f"  Local scraper: Fetching Amazon search for '{query}'...")
            await page.goto(url, timeout=20000, wait_until="domcontentloaded")

            # Random human-like delay
            await page.wait_for_timeout(random.randint(1200, 2500))
            await page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=12000)

            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            results = []
            items = soup.find_all('div', {'data-component-type': 's-search-result'})
            for item in items[:5]:  # Check top 5 results
                title_elem = item.find('h2')
                price_elem = item.find('span', class_='a-price-whole')
                # Broader link selector to handle Amazon's varying class names
                link_elem = item.find('a', class_='a-link-normal')

                if title_elem and price_elem and link_elem:
                    title = title_elem.text.strip()
                    price_str = price_elem.text.strip().replace(',', '').replace('.', '')
                    try:
                        price = float(price_str)
                    except ValueError:
                        continue

                    link = "https://www.amazon.in" + link_elem.get('href', '')
                    category = guess_category(title)
                    commission = price * COMMISSION_RATES[category]

                    results.append({
                        "platform": "Amazon",
                        "search_query": query,
                        "title": title,
                        "price": price,
                        "url": link,
                        "estimated_commission_inr": round(commission, 2)
                    })

            await browser.close()
            return results

        except Exception as e:
            print(f"  Local scraper failed for '{query}': {e}")
            await browser.close()
            return []

def get_best_product(products_list):
    """
    Searches Amazon for a list of products and returns the one
    with the highest estimated commission.
    """
    all_results = []

    for product in products_list:
        print(f"Scraping affiliate data for: {product}")
        results = asyncio.run(search_amazon(product))
        all_results.extend(results)
        if results:
            print(f"  Found {len(results)} result(s) for '{product}'.")

    if not all_results:
        print("Warning: Local scraper returned no results. Amazon may have updated its anti-bot measures.")
        return None

    # Filter out already used products to prevent content collision
    from app.utils.db_tracker import is_product_used
    filtered_results = []
    for item in all_results:
        if is_product_used(item['url']):
            print(f"  DB Tracker: Product already processed in a previous run, skipping: {item['title']}")
        else:
            filtered_results.append(item)

    if not filtered_results:
        print("Warning: All scraped products were already processed in previous runs. Falling back to entire list to avoid aborting pipeline.")
        filtered_results = all_results

    # Sort by highest estimated commission
    best_product = sorted(filtered_results, key=lambda x: x['estimated_commission_inr'], reverse=True)[0]
    return best_product

if __name__ == "__main__":
    best = get_best_product(["Wireless Earbuds", "Air Fryer"])
    print("Best product found:", best)
