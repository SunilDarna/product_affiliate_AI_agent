import os
import random
import yt_dlp
import re
from app.config import WORKSPACE_DIR

# Randomized user agents — mirroring ShortsAutomatorAIAgent local scraper
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def extract_brand_name(product_title):
    """
    Leverages Google Gemini Flash to extract the primary proper noun brand name of the product
    from the Amazon title to ensure accurate search terms and uploader validation.
    """
    try:
        from google import genai
        from google.genai import types
        from app.config import GEMINI_API_KEY
        
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")

        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Given the following Amazon product title, extract the primary brand name of the product.
        Return ONLY the brand name as a single word or short proper noun (e.g. "Ninja", "Ulanzi", "HIFFIN", "Noise", "Boat", "Digitek").
        Do not include any punctuation, quotes, or explanatory text.
        
        Product Title: "{product_title}"
        """
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0)
        )
        brand = response.text.strip().replace('"', '').replace("'", "")
        print(f"Gemini extracted brand name: '{brand}'")
        return brand
    except Exception as e:
        print(f"Failed to extract brand via Gemini: {e}")
        # Robust heuristic fallback: use the first word of the product title
        first_word = product_title.split()[0] if product_title else "Brand"
        # Clean any punctuation
        first_word = re.sub(r'[^a-zA-Z0-9]', '', first_word)
        print(f"Fallback extracted brand name: '{first_word}'")
        return first_word

def search_and_download_ad(product_name):
    """
    Searches YouTube for an official brand commercial/ad of the product.
    Strictly verifies that the uploader channel title contains the brand name
    (case-insensitive) to prevent copyright issues from third-party creator videos.

    If an official brand video is found, downloads it and returns the absolute path.
    Otherwise, returns None to trigger the official product image slideshow fallback.
    """
    from app.utils.db_tracker import is_clip_used, record_clip

    brand = extract_brand_name(product_name)
    
    # Trim to first 4 words for a clean search query
    short_name = " ".join(product_name.split()[:4])
    output_template = os.path.join(WORKSPACE_DIR, 'raw_clip_%(id)s.%(ext)s')

    # Step 1: Search metadata-only (download=False) to identify a brand-official clip
    ydl_opts_search = {
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
        'nocheckcertificate': True,
        'user_agent': random.choice(USER_AGENTS),
    }

    selected_video_id = None
    selected_video_title = ""
    selected_video_duration = 0

    # Build brand-safe search queries prioritizing official product ads
    search_queries = [
        f"ytsearch5:{brand} {short_name} official ad",
        f"ytsearch5:{brand} {short_name} commercial",
        f"ytsearch5:{brand} {short_name} product video"
    ]

    for sq in search_queries:
        if selected_video_id:
            break
        try:
            print(f"Searching YouTube for official brand video: '{sq}'...")
            with yt_dlp.YoutubeDL(ydl_opts_search) as ydl:
                info = ydl.extract_info(sq, download=False)
                
                if info and 'entries' in info:
                    for entry in info['entries']:
                        if not entry:
                            continue
                        video_id = entry.get('id')
                        duration = entry.get('duration', 999) or 0
                        title = entry.get('title', '')
                        uploader = entry.get('uploader', '')
                        
                        # Apply Brand Official Uploader Verification Filter
                        uploader_lower = uploader.lower() if uploader else ""
                        brand_lower = brand.lower()
                        
                        if brand_lower not in uploader_lower:
                            print(f"  [Brand Filter Bypass] Skipping review clip '{title}' uploaded by '{uploader}' (does not match brand '{brand}')")
                            continue

                        # Check if clip is unused and between 10s and 20 mins
                        if 10 < duration < 1200:
                            if is_clip_used(video_id):
                                print(f"  DB Tracker: Official clip {video_id} ('{title}') was already used. Skipping...")
                                continue
                            
                            selected_video_id = video_id
                            selected_video_title = title
                            selected_video_duration = duration
                            print(f"  DB Tracker: Selected unused official brand video: {video_id} ('{title}') by '{uploader}' - Duration: {duration}s")
                            break
                            
        except Exception as e:
            print(f"Error during official video search for '{sq}': {e}")

    if not selected_video_id:
        print(f"\n❌ [Sourcing Succeeded Check] No official brand video found on YouTube for brand '{brand}'.")
        print("   Proceeding to trigger the high-resolution Amazon product images slideshow fallback.")
        return None

    # Step 2: Download the selected official brand clip
    download_url = f"https://www.youtube.com/watch?v={selected_video_id}"
    ydl_opts_download = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
        'nocheckcertificate': True,
        'socket_timeout': 120,
        'retries': 15,
        'user_agent': random.choice(USER_AGENTS),
    }

    try:
        print(f"Downloading selected official brand video: {download_url}")
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            info = ydl.extract_info(download_url, download=True)
            filename = ydl.prepare_filename(info)
            
            def save_info_json(filepath):
                import json
                info_json_path = os.path.splitext(filepath)[0] + ".info.json"
                meta = {
                    "title": info.get("title", ""),
                    "description": info.get("description", ""),
                    "duration": info.get("duration", 0.0),
                    "chapters": info.get("chapters", [])
                }
                try:
                    with open(info_json_path, "w", encoding="utf-8") as f:
                        json.dump(meta, f, indent=2, ensure_ascii=False)
                    print(f"Saved companion metadata to {info_json_path}")
                except Exception as ex:
                    print(f"Error saving companion metadata: {ex}")

            # Check for the downloaded file with standard extensions
            for ext in ['.mp4', '.webm', '.mkv']:
                candidate = os.path.splitext(filename)[0] + ext
                if os.path.exists(candidate):
                    record_clip(selected_video_id, selected_video_title, int(selected_video_duration))
                    print(f"Successfully downloaded and tracked: {candidate}")
                    save_info_json(candidate)
                    return candidate
            
            if os.path.exists(filename):
                record_clip(selected_video_id, selected_video_title, int(selected_video_duration))
                print(f"Successfully downloaded and tracked: {filename}")
                save_info_json(filename)
                return filename

    except Exception as e:
        print(f"Error downloading selected video {selected_video_id}: {e}")

    return None

if __name__ == "__main__":
    clip_path = search_and_download_ad("Boat Airdopes")
    print("Downloaded to:", clip_path)
