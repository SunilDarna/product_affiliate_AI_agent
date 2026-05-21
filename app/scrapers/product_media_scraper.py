import os
import re
import random
import requests
import asyncio
from playwright.async_api import async_playwright
from app.config import WORKSPACE_DIR

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def clean_amazon_image_url(url: str) -> str:
    """
    Strips Amazon's custom crop/resize suffixes to get the original high-resolution photo.
    Example:
    - https://m.media-amazon.com/images/I/51cBpxsZR4L._AC_QL10_SX980_SY55_.jpg
    -> https://m.media-amazon.com/images/I/51cBpxsZR4L.jpg
    """
    # Remove standard Amazon sizing segments (e.g. ._AC_QL10_SX980_SY55_.)
    cleaned = re.sub(r'\._[A-Za-z0-9-_%,+.]+_\.', '.', url)
    cleaned = re.sub(r'\._[A-Z0-9-_%.+]+_\.', '.', cleaned)
    # Ensure standard extensions are clean
    cleaned = re.sub(r'\.+jpg$', '.jpg', cleaned)
    cleaned = re.sub(r'\.+png$', '.png', cleaned)
    cleaned = re.sub(r'\.+jpeg$', '.jpeg', cleaned)
    return cleaned

async def scrape_amazon_listing_images(product_url: str) -> list:
    """
    Opens the Amazon product details page and extracts all original high-resolution
    marketing and showcase images from the page source.
    """
    print(f"Scraping Amazon listing images from: {product_url}")
    
    # We do not block images here because loading them ensures all javascript elements
    # and lazy-loaded image blocks are hydrated correctly in page source.
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS) if USER_AGENTS else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="en-IN",
        )
        page = await context.new_page()
        
        try:
            await page.goto(product_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(1500, 3000))
            content = await page.content()
        except Exception as e:
            print(f"Playwright Amazon page fetch error: {e}")
            content = ""
        finally:
            await browser.close()
            
    if not content:
        return []

    images = []
    
    # Primary: Look for colorImages script block
    color_images_match = re.search(r"'colorImages'\s*:\s*(\{[^;]+?\})\s*,\s*'colorMap'", content)
    if not color_images_match:
        color_images_match = re.search(r"colorImages\s*=\s*(\{[^;]+?\});", content)
        
    if color_images_match:
        try:
            js_obj = color_images_match.group(1)
            hi_res_urls = re.findall(r'"hiRes"\s*:\s*"([^"]+)"', js_obj)
            large_urls = re.findall(r'"large"\s*:\s*"([^"]+)"', js_obj)
            for img in hi_res_urls + large_urls:
                if img:
                    images.append(img)
        except Exception as e:
            print(f"Error parsing colorImages script block: {e}")
            
    # Secondary: Fallback to raw regex matching on media-amazon/images-amazon links
    fallback_matches = re.findall(r'https?://[a-zA-Z0-9.-]*amazon\.com/images/I/[a-zA-Z0-9-_%+.]+?\.(?:jpg|png|jpeg)', content)
    for img in fallback_matches:
        images.append(img)

    # Clean and deduplicate images
    cleaned_images = []
    for img in images:
        cleaned_url = clean_amazon_image_url(img)
        
        # Exclude icons, badges, banners, logos, sizing charts, or other non-product graphics
        lower_url = cleaned_url.lower()
        if any(bad in lower_url for bad in ["icon", "badge", "logo", "banner", "sprite", "rating", "chart", "button", "checkmark"]):
            continue
            
        if cleaned_url not in cleaned_images:
            cleaned_images.append(cleaned_url)
            
    print(f"Extracted {len(cleaned_images)} high-resolution brand images.")
    return cleaned_images

def download_product_images(product_url: str, max_images: int = 8) -> list:
    """
    Synchronous wrapper to scrape and download Amazon listing images.
    Saves them locally to WORKSPACE_DIR and returns a list of local file paths.
    """
    image_urls = asyncio.run(scrape_amazon_listing_images(product_url))
    if not image_urls:
        print("Warning: No product images found to download.")
        return []

    downloaded_paths = []
    
    # Ensure workspace directory exists
    images_dir = os.path.join(WORKSPACE_DIR, "scraped_images")
    os.makedirs(images_dir, exist_ok=True)
    
    # Clean previous scraped images to prevent conflicts
    for file in os.listdir(images_dir):
        try:
            os.remove(os.path.join(images_dir, file))
        except:
            pass

    count = 0
    for url in image_urls:
        if count >= max_images:
            break
            
        try:
            # Determine extension
            ext = ".jpg"
            if ".png" in url.lower():
                ext = ".png"
            elif ".jpeg" in url.lower():
                ext = ".jpeg"
                
            dest_path = os.path.join(images_dir, f"slide_{count}{ext}")
            print(f"Downloading image {count}: {url} -> {dest_path}")
            
            # Simple HTTP download with timeout
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(resp.content)
                downloaded_paths.append(dest_path)
                count += 1
            else:
                print(f"Failed to download image {url}: status code {resp.status_code}")
        except Exception as e:
            print(f"Failed to download image {url}: {e}")

    print(f"Successfully downloaded {len(downloaded_paths)} product images.")
    return downloaded_paths

if __name__ == "__main__":
    test_url = "https://www.amazon.in/dp/B0FWY8TT1X"
    paths = download_product_images(test_url)
    print("Downloaded image paths:", paths)
