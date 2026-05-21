import asyncio
import re
import datetime
import requests
from playwright.async_api import async_playwright
from app.utils.browser_helper import ensure_chrome_debugging_active
from app.config import YOUTUBE_CHANNEL_HANDLE

def parse_date(date_str):
    """
    Parses dynamic date strings like 'May 18, 2026', '1 day ago', '12 hours ago'
    into a datetime.date object. Returns None if parsing fails.
    """
    if not date_str:
        return None
        
    # Split by newline and take the first line to get only the date portion (e.g. '23 Dec 2024\nUploaded')
    lines = [line.strip() for line in date_str.split("\n") if line.strip()]
    if not lines:
        return None
    date_str = lines[0].lower().strip()
    
    today = datetime.date.today()
    
    if "ago" in date_str:
        if "hour" in date_str or "minute" in date_str:
            return today
        elif "day" in date_str:
            try:
                days = int(re.search(r'(\d+)', date_str).group(1))
                return today - datetime.timedelta(days=days)
            except:
                return today
                
    # Normalize separators: replace commas, hyphens, and slashes with spaces
    normalized = date_str.replace(",", " ").replace("-", " ").replace("/", " ")
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    
    try:
        # 1. Match: Month Name, Day, Year (e.g. "dec 23 2024")
        match = re.search(r'([a-z]{3})[a-z]*\s+(\d+)\s+(\d{4})', normalized)
        if match:
            month_name, day, year = match.groups()
            if month_name in months:
                return datetime.date(int(year), months[month_name], int(day))
                
        # 2. Match: Day, Month Name, Year (e.g. "23 dec 2024")
        match = re.search(r'(\d+)\s+([a-z]{3})[a-z]*\s+(\d{4})', normalized)
        if match:
            day, month_name, year = match.groups()
            if month_name in months:
                return datetime.date(int(year), months[month_name], int(day))
                
        # 3. Match: Year, Month Name, Day (e.g. "2024 dec 23")
        match = re.search(r'(\d{4})\s+([a-z]{3})[a-z]*\s+(\d+)', normalized)
        if match:
            year, month_name, day = match.groups()
            if month_name in months:
                return datetime.date(int(year), months[month_name], int(day))
                
        # 4. Match numeric: YYYY MM DD (e.g. "2024 12 23")
        match = re.search(r'^(\d{4})\s+(\d{1,2})\s+(\d{1,2})$', normalized)
        if match:
            year, month, day = match.groups()
            return datetime.date(int(year), int(month), int(day))
            
        # 5. Match numeric: DD MM YYYY or MM DD YYYY (e.g. "23 12 2024")
        match = re.search(r'^(\d{1,2})\s+(\d{1,2})\s+(\d{4})$', normalized)
        if match:
            first, second, year = match.groups()
            if int(first) > 12:
                return datetime.date(int(year), int(second), int(first))
            elif int(second) > 12:
                return datetime.date(int(year), int(first), int(second))
            else:
                try:
                    return datetime.date(int(year), int(second), int(first))
                except:
                    return datetime.date(int(year), int(first), int(second))
    except Exception as e:
        print(f"Error parsing date string '{date_str}' (normalized: '{normalized}'): {e}")
        
    return None

def parse_number(num_str):
    """
    Converts string metrics like '1.2K', '450', '2M' into standard integers.
    """
    num_str = num_str.strip().upper().replace(',', '')
    if not num_str:
        return 0
    try:
        if 'M' in num_str:
            return int(float(num_str.replace('M', '')) * 1000000)
        elif 'K' in num_str:
            return int(float(num_str.replace('K', '')) * 1000)
        return int(float(num_str))
    except:
        return 0

async def switch_channel_if_needed(page, target_handle=None):
    """
    Checks if the active YouTube Studio channel matches the target handle.
    If not, automates switching to the target channel.
    """
    if target_handle is None:
        target_handle = YOUTUBE_CHANNEL_HANDLE
        
    print(f"Checking if active YouTube Studio channel is {target_handle}...")
    
    # Mapping of handles to known Channel IDs for direct URL checking
    CHANNEL_IDS = {
        "@cloudtechtrends": "UCTynXOGpihxhmCRdt7iA5wA",
        "cloudtechtrends": "UCTynXOGpihxhmCRdt7iA5wA",
        "@darnasunil303": "UCX3apgaScNxNRkbWZifZsww",
        "darnasunil303": "UCX3apgaScNxNRkbWZifZsww"
    }
    
    target_id = CHANNEL_IDS.get(target_handle.lower())
    if target_id:
        current_url = page.url
        if f"/channel/{target_id}" in current_url:
            print(f"✅ URL verification success: Already logged into the correct channel ID {target_id} ({target_handle})")
            return True
        
    try:
        # Step 1: Click the profile avatar button at top right
        avatar_btn = await page.wait_for_selector("#avatar-btn", timeout=15000)
        if not avatar_btn:
            print("Could not find avatar button. Skipping channel switch check.")
            return False
            
        await avatar_btn.click()
        await page.wait_for_timeout(2000)
        
        # Step 2: Read the active handle inside the user menu
        menu_handle_elem = await page.query_selector("#channel-handle, #email, #channel-title, .channel-title")
        current_handle = ""
        if menu_handle_elem:
            current_handle = await menu_handle_elem.inner_text()
            current_handle = current_handle.strip().lower()
            print(f"Active user menu handle/details: '{current_handle}'")
            
        clean_target = target_handle.lower().strip("@")
        if clean_target in current_handle:
            print(f"Already logged into the correct target channel: {target_handle}")
            # Click avatar button again to close user menu
            await avatar_btn.click()
            await page.wait_for_timeout(1000)
            return True
            
        # Step 3: Target channel not active. Attempting to switch account.
        print(f"Target channel {target_handle} is not active. Attempting to switch channel...")
        
        # Look for "Switch account" in the menu
        items = await page.query_selector_all("ytd-compact-link-renderer, tp-yt-paper-item, #endpoint")
        switch_btn = None
        for item in items:
            text = await item.inner_text()
            if "switch account" in text.lower() or "खाता बदलें" in text.lower():
                switch_btn = item
                break
                
        if not switch_btn:
            switch_btn = await page.query_selector("text=Switch account")
            
        if not switch_btn:
            print("Could not find 'Switch account' option in user menu.")
            await avatar_btn.click()
            return False
            
        print("Clicking 'Switch Account' button...")
        await switch_btn.click()
        await page.wait_for_timeout(3000)
        
        # Step 4: Wait for the switcher list and click the target channel
        channel_items = await page.query_selector_all("ytd-account-item-renderer, tp-yt-paper-item, paper-item, ytd-compact-link-renderer")
        target_item = None
        print(f"Found {len(channel_items)} channel items in switch list. Looking for '{target_handle}'...")
        
        for item in channel_items:
            text = await item.inner_text()
            if clean_target in text.lower():
                target_item = item
                print(f"Found target channel item: '{text.strip()}'")
                break
                
        if not target_item:
            target_item = await page.query_selector(f"text={clean_target}")
            if not target_item:
                target_item = await page.query_selector(f"text={target_handle}")
                
        if target_item:
            print(f"Clicking on target channel '{target_handle}' to switch...")
            await target_item.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await target_item.click(force=True)
            # Wait for reload and stabilizing page
            await page.wait_for_timeout(8000)
            print("Channel switch triggered successfully.")
            return True
        else:
            print(f"Could not find target channel '{target_handle}' in the accounts switcher list.")
            await page.click("body", position={"x": 10, "y": 10})
            return False
            
    except Exception as e:
        print(f"Error switching channel: {e}")
        try:
            await page.click("body", position={"x": 10, "y": 10})
        except:
            pass
        return False


def scrape_youtube_studio_analytics_api(target_handle="@cloudtechtrends"):
    """
    Scrapes recent uploads within the past 15 days directly via the official YouTube Data API.
    """
    from app.config import YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
    
    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET or not YOUTUBE_REFRESH_TOKEN:
        raise Exception("YouTube OAuth credentials not fully configured in config/secrets.")
        
    # 1. Get access token
    url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "refresh_token": YOUTUBE_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(url, data=payload, timeout=10)
    if response.status_code != 200:
        raise Exception(f"Failed to refresh access token: {response.text}")
    access_token = response.json().get("access_token")
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    # 2. Get active channels list
    channels_url = "https://www.googleapis.com/youtube/v3/channels?part=snippet,contentDetails,statistics&mine=true"
    response = requests.get(channels_url, headers=headers, timeout=10)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch channels: {response.text}")
        
    channels_data = response.json().get("items", [])
    if not channels_data:
        raise Exception("No channels found for the provided credentials.")
        
    active_channel = channels_data[0]
    if target_handle:
        clean_target = target_handle.lower().strip("@")
        for channel in channels_data:
            title = channel["snippet"]["title"]
            custom_url = channel["snippet"].get("customUrl", "")
            clean_custom = custom_url.lower().strip("@")
            if clean_target == clean_custom or clean_target in title.lower():
                active_channel = channel
                break
                
    channel_title = active_channel["snippet"]["title"]
    sub_count = int(active_channel["statistics"].get("subscriberCount", "0"))
    uploads_playlist_id = active_channel["contentDetails"]["relatedPlaylists"]["uploads"]
    
    print(f"YouTube Data API: Targeting channel '{channel_title}' (ID: {active_channel['id']})")
    
    # 3. Fetch recent uploads
    playlist_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails&playlistId={uploads_playlist_id}&maxResults=50"
    response = requests.get(playlist_url, headers=headers, timeout=10)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch playlist items: {response.text}")
        
    playlist_items = response.json().get("items", [])
    
    today = datetime.datetime.now(datetime.timezone.utc)
    cutoff_date = today - datetime.timedelta(days=15)
    
    video_ids = []
    video_snippet_map = {}
    
    for item in playlist_items:
        published_at_str = item["snippet"]["publishedAt"]
        published_at = datetime.datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
        
        if published_at >= cutoff_date:
            v_id = item["contentDetails"]["videoId"]
            video_ids.append(v_id)
            video_snippet_map[v_id] = {
                "title": item["snippet"]["title"],
                "publishedAt": published_at.date().isoformat()
            }
            
    if not video_ids:
        print("YouTube Data API: No videos found uploaded in the past 15 days.")
        return {
            "subscriber_count": sub_count,
            "scraped_at": datetime.datetime.now().isoformat(),
            "videos": []
        }
        
    # 4. Fetch detailed stats & check duration to isolate Shorts
    stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,contentDetails&id={','.join(video_ids)}"
    response = requests.get(stats_url, headers=headers, timeout=10)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch video statistics: {response.text}")
        
    videos_details = response.json().get("items", [])
    
    def parse_duration_seconds(duration_str):
        match = re.match(r'PT(?:(\d+)M)?(?:(\d+)S)?', duration_str)
        if not match:
            return 0
        minutes = int(match.group(1)) if match.group(1) else 0
        seconds = int(match.group(2)) if match.group(2) else 0
        return (minutes * 60) + seconds
        
    shorts_data = []
    for video in videos_details:
        v_id = video["id"]
        duration_str = video["contentDetails"]["duration"]
        duration_seconds = parse_duration_seconds(duration_str)
        
        # Shorts are defined as videos <= 60 seconds
        if duration_seconds > 60:
            print(f"YouTube Data API: Skipping long-form video '{video_snippet_map[v_id]['title']}' ({duration_seconds}s)")
            continue
            
        stats = video.get("statistics", {})
        views = int(stats.get("viewCount", "0"))
        likes = int(stats.get("likeCount", "0"))
        comments = int(stats.get("commentCount", "0"))
        
        shorts_data.append({
            "title": video_snippet_map[v_id]["title"],
            "date": video_snippet_map[v_id]["publishedAt"],
            "views": views,
            "likes": likes,
            "comments": comments,
            "retention": None
        })
        
    return {
        "subscriber_count": sub_count,
        "scraped_at": datetime.datetime.now().isoformat(),
        "videos": shorts_data
    }


async def scrape_youtube_studio_analytics(target_handle="@cloudtechtrends"):
    """
    Retrieves recent uploads within the past 15 days using either the YouTube API (primary)
    or automated browser scraping of YouTube Studio (fallback).
    """
    # 1. Primary Method: Fetch directly via official YouTube API
    try:
        print(f"Attempting to fetch analytics via YouTube Data API for channel '{target_handle}'...")
        api_stats = scrape_youtube_studio_analytics_api(target_handle)
        print(f"✅ Success: Retrieved {len(api_stats['videos'])} Shorts via official YouTube API.")
        return api_stats
    except Exception as api_err:
        print(f"⚠️ YouTube Data API method failed: {api_err}")
        print("Falling back to Playwright browser scraper of YouTube Studio...")

    # 2. Fallback Method: Browser Scraper
    # Ensure Chrome debugging is active before attempting to connect
    ensure_chrome_debugging_active()
    
    async with async_playwright() as p:
        page = None
        try:
            print(f"Connecting to running Chrome via CDP to scrape YouTube Studio channel '{target_handle}'...")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            
            # Access default context and open a new page
            context = browser.contexts[0]
            page = await context.new_page()
            
            # Block heavy resources like images and media to ensure fast scraping, but keep fonts active for styling
            await page.route("**/*", lambda route: route.abort()
                if route.request.resource_type in ["image", "media"]
                else route.continue_()
            )
            
            # Navigate to YouTube Studio home page to resolve the active channel ID
            print("Navigating to YouTube Studio...")
            await page.goto("https://studio.youtube.com", timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
            # Dynamically switch channel to the target channel if not active
            switched = await switch_channel_if_needed(page, target_handle)
            if switched:
                print("Re-navigating to Studio home to resolve the newly active channel URL...")
                await page.goto("https://studio.youtube.com", timeout=40000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
            
            current_url = page.url
            print(f"Resolved Studio URL: {current_url}")
            
            # Extract channel ID using regex
            channel_match = re.search(r'/channel/(UC[a-zA-Z0-9_-]+)', current_url)
            if not channel_match:
                print("Could not resolve Channel ID. Navigating to general content path...")
                content_url = "https://studio.youtube.com/videos"
            else:
                channel_id = channel_match.group(1)
                content_url = f"https://studio.youtube.com/channel/{channel_id}/videos"
                print(f"Extracted Channel ID: {channel_id}")
                
            # Navigate to the standard Content page first to avoid SPA routing issues
            print(f"Navigating to Content page: {content_url}")
            await page.goto(content_url, timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            
            # Explicitly find and click the "Shorts" tab to switch view
            print("Locating 'Shorts' tab element on Content page...")
            try:
                shorts_locator = page.locator('text="Shorts"')
                count = await shorts_locator.count()
                clicked = False
                for i in range(count):
                    el = shorts_locator.nth(i)
                    if await el.is_visible():
                        print(f"Clicking visible 'Shorts' element at index {i}...")
                        await el.click(force=True)
                        clicked = True
                        break
                
                if clicked:
                    await page.wait_for_timeout(4000)
                else:
                    print("Could not click 'Shorts' element via text locator. Trying fallback selectors...")
                    # Fallback selectors
                    selectors = [
                        'ytcp-text-menu-item[label-text="Shorts"]',
                        'paper-tab:has-text("Shorts")',
                        'ytcp-text-menu-item:has-text("Shorts")',
                        '[id="navigation-item-shorts"]'
                    ]
                    for selector in selectors:
                        try:
                            shorts_tab = await page.query_selector(selector)
                            if shorts_tab and await shorts_tab.is_visible():
                                print(f"Found Shorts tab fallback selector: {selector}")
                                await shorts_tab.click(force=True)
                                await page.wait_for_timeout(4000)
                                clicked = True
                                break
                        except Exception:
                            continue
            except Exception as tab_error:
                print(f"Error trying to click Shorts sub-tab: {tab_error}")
            
            # Wait for video rows or empty state container to load
            try:
                print("Waiting for video rows to render...")
                await page.wait_for_selector("ytcp-video-row, #no-videos-container, .no-videos", timeout=15000)
            except Exception as wait_error:
                print(f"Note: Wait for video rows selector timed out: {wait_error}. Proceeding with active DOM rows...")
                
            await page.wait_for_timeout(2000)
            
            # Capture a screenshot for diagnostic verification
            import os
            screenshot_path = "/Users/sunildarna/.gemini/antigravity/browser_recordings/youtube_shorts_page.png"
            try:
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                await page.screenshot(path=screenshot_path)
                print(f"Diagnostic screenshot saved to {screenshot_path}")
            except Exception as screenshot_err:
                print(f"Note: Could not save diagnostic screenshot: {screenshot_err}")
            
            # Scrape active subscriber count from the mini-sidebar if visible
            sub_count = 0
            try:
                sub_element = await page.query_selector("div.subscriber-count, #subscriber-count")
                if sub_element:
                    sub_text = await sub_element.inner_text()
                    sub_count = parse_number(sub_text)
                    print(f"Current Subscriber Count: {sub_count}")
            except Exception as e:
                print(f"Note: Could not scrape subscriber count: {e}")
            
            # Select all video rows (ytcp-video-row is YouTube's custom element tag)
            rows = await page.query_selector_all("ytcp-video-row")
            print(f"Found {len(rows)} video rows on Content page.")
            
            video_data = []
            today = datetime.date.today()
            cutoff_date = today - datetime.timedelta(days=15)
            
            for row in rows:
                try:
                    # 1. Extract Title
                    title = "Unknown Title"
                    checkbox_elem = await row.query_selector("ytcp-checkbox-lit")
                    if checkbox_elem:
                        aria_label = await checkbox_elem.get_attribute("aria-label")
                        if aria_label and aria_label.strip().lower().startswith("select "):
                            title = aria_label[len("Select "):].strip()
                    
                    if title == "Unknown Title" or not title:
                        title_elem = await row.query_selector("a#video-title-anchor, .video-title-anchor, #video-title")
                        if title_elem:
                            title = await title_elem.inner_text()
                        else:
                            # Final fallback: first anchor or text
                            title_elem = await row.query_selector(".tablecell-video a")
                            title = await title_elem.inner_text() if title_elem else "Unknown Title"
                    title = title.strip()
                    
                    # 2. Extract Date
                    date_elem = await row.query_selector("div#date-cell, .cell-body-text.date, td.column-date, .tablecell-date, [role='cell'].tablecell-date")
                    if not date_elem:
                        row_text = await row.inner_text()
                        print(f"Warning: Could not find date element in row. Row text snippet: '{row_text[:100].replace(chr(10), ' ')}...'")
                    date_text = await date_elem.inner_text() if date_elem else "Today"
                    date_text = date_text.strip()
                    upload_date = parse_date(date_text) or today
                    
                    # Check if the upload is older than 15 days
                    if upload_date < cutoff_date:
                        # Since list is sorted chronologically descending, we can stop scraping
                        print(f"Stopping scrape: '{title}' uploaded on {upload_date} is older than 15 days (cutoff: {cutoff_date})")
                        break
                        
                    # 3. Extract Views
                    views_elem = await row.query_selector("div#views-cell, td.column-views, .column-views, .tablecell-views, [role='cell'].tablecell-views")
                    views_text = await views_elem.inner_text() if views_elem else "0"
                    views = parse_number(views_text)
                    
                    # 4. Extract Likes
                    likes_elem = await row.query_selector("div#likes-cell, td.column-likes, .column-likes, .tablecell-likes, .tablecell-rating, .tablecell-likes-percentage, [role='cell'].tablecell-likes")
                    likes_text = await likes_elem.inner_text() if likes_elem else "0"
                    likes = parse_number(likes_text)
                    
                    # 5. Extract Comments (optional/fallback)
                    comments_elem = await row.query_selector("div#comments-cell, td.column-comments, .column-comments, .tablecell-comments, [role='cell'].tablecell-comments")
                    comments_text = await comments_elem.inner_text() if comments_elem else "0"
                    comments = parse_number(comments_text)
                    
                    # 6. Gather average view percentage / retention if visible
                    # Note: YouTube Studio sometimes has average view duration columns depending on column settings.
                    # We default to None if not visible, which our analyzer can handle.
                    retention = None
                    retention_elem = await row.query_selector(".column-average-view-duration, td.column-average-view-duration, .tablecell-average-view-duration")
                    if retention_elem:
                        retention_text = await retention_elem.inner_text()
                        retention = retention_text.strip()
                        
                    print(f"Scraped Row -> Title: '{title}', Views: {views}, Likes: {likes}, Date: {upload_date}")
                    video_data.append({
                        "title": title,
                        "date": upload_date.isoformat(),
                        "views": views,
                        "likes": likes,
                        "comments": comments,
                        "retention": retention
                    })
                    
                except Exception as row_error:
                    print(f"Error scraping a specific video row: {row_error}")
                    continue
                    
            await page.close()
            print(f"Scrape completed successfully. Scraped {len(video_data)} videos within the 15-day window.")
            return {
                "subscriber_count": sub_count,
                "scraped_at": datetime.datetime.now().isoformat(),
                "videos": video_data
            }
            
        except Exception as e:
            print(f"YouTube Studio Scraper failed: {e}")
            if page:
                try:
                    await page.close()
                except:
                    pass
            # Return empty structure rather than crashing pipeline
            return {
                "subscriber_count": 0,
                "scraped_at": datetime.datetime.now().isoformat(),
                "videos": []
            }

if __name__ == "__main__":
    # Test runner
    import sys
    handle = "@cloudtechtrends"
    if len(sys.argv) > 1:
        handle = sys.argv[1]
    print(f"Testing YouTube Studio Scraper locally for channel: {handle}...")
    stats = asyncio.run(scrape_youtube_studio_analytics(handle))
    print("Scraped Stats Result:", stats)
