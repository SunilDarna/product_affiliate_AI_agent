import asyncio
import sys
from app.scrapers.youtube_studio_scraper import scrape_youtube_studio_analytics
from app.config import YOUTUBE_CHANNEL_HANDLE

async def test_main():
    print("=" * 60)
    print(f"      TESTING YOUTUBE STUDIO SCRAPER FOR {YOUTUBE_CHANNEL_HANDLE}      ")
    print("=" * 60)
    
    print("[*] Launching YouTube Studio Scraper...")
    try:
        raw_analytics = await scrape_youtube_studio_analytics(YOUTUBE_CHANNEL_HANDLE)
        print("\n" + "=" * 50)
        print("                 TEST RESULT                 ")
        print("=" * 50)
        print(f"[+] Scraped at: {raw_analytics.get('scraped_at')}")
        print(f"[+] Subscriber Count: {raw_analytics.get('subscriber_count', 0)}")
        
        videos = raw_analytics.get('videos', [])
        print(f"[+] Found {len(videos)} videos uploaded in the past 15 days:")
        for idx, video in enumerate(videos):
            print(f"    {idx+1}. ID: {video.get('id', 'N/A')} - Title: '{video.get('title', 'N/A')}'")
            print(f"       Published: {video.get('publishedAt', 'N/A')} | Views: {video.get('views', 0)}")
        print("=" * 50)
        print("[+] Scraper verification completed successfully!")
        
    except Exception as e:
        print(f"\n[-] Scraper test encountered an error: {e}")
        print("    If it failed the browser scraping fallback, make sure you have Google Chrome open")
        print("    in remote debugging mode on port 9222.")

if __name__ == "__main__":
    asyncio.run(test_main())
