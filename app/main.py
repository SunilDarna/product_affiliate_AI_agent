import os
import uvicorn
import asyncio
from fastapi import FastAPI, BackgroundTasks

from app.scrapers.trend_analyzer import get_trending_topics_india
from app.scrapers.affiliate_scraper import get_best_product
from app.video.downloader import search_and_download_ad
from app.video.editor import strip_audio
from app.llm.script_generator import generate_scripts
from app.video.tts import create_voiceover
from app.video.composer import compose_final_video
from app.publish.link_generator import generate_affiliate_link
from app.publish.seo_generator import generate_seo_metadata
from app.publish.uploader import upload_to_youtube, upload_to_instagram

from app.config import YOUTUBE_CHANNEL_HANDLE

# New performance learning loop imports
from app.scrapers.youtube_studio_scraper import scrape_youtube_studio_analytics
from app.analytics.performance_analyzer import run_performance_analysis

app = FastAPI(title="Product Affiliate AI Agent", description="Autonomous pipeline for affiliate shorts")

def run_pipeline():
    print("\n=== STARTING PRODUCT AFFILIATE PIPELINE ===")
    
    # Initialize the SQLite tracking database for conflict prevention
    from app.utils.db_tracker import init_db, record_product
    init_db()
    
    # Phase 1: YouTube Performance Analysis & Learning Loop
    print(f"\n[1/7] Scraping YouTube Studio Analytics for {YOUTUBE_CHANNEL_HANDLE} (Active CDP Session)...")
    try:
        raw_analytics = asyncio.run(scrape_youtube_studio_analytics(YOUTUBE_CHANNEL_HANDLE))
        if raw_analytics and raw_analytics.get("videos"):
            print(f"Found {len(raw_analytics['videos'])} video(s) uploaded in the past 15 days. Running performance synthesis...")
            learnings = run_performance_analysis(raw_analytics)
            if learnings:
                print("Performance analysis complete. Channel learnings saved successfully.")
        else:
            print("No videos found from the past 15 days on the channel. Skipping performance analysis and proceeding with robust base LLM product selection.")
    except Exception as e:
        print(f"Phase 1 Performance Loop failed (Pipeline continuing): {e}")
    
    # Phase 2: Trend Discovery & Scraping
    print("\n[2/7] Discovering Trends...")
    trends = get_trending_topics_india()
    print(f"Discovered Trends: {trends}")
    
    print("\n[3/7] Scraping Affiliate Platforms...")
    best_product = get_best_product(trends)
    if not best_product:
        print("No suitable high-commission product found. Aborting pipeline.")
        return
    print(f"Selected Product: {best_product['title']} (Est. Commission: ₹{best_product['estimated_commission_inr']})")
    
    # Track the product in database to avoid duplicate selection in future runs
    record_product(
        title=best_product['title'],
        url=best_product['url'],
        platform=best_product['platform'],
        price=best_product['price'],
        commission=best_product['estimated_commission_inr']
    )
    
    # Phase 3: Video Sourcing
    print("\n[4/7] Sourcing Video Clip...")
    video_path = search_and_download_ad(best_product['title'])
    
    image_paths = None
    silent_video = None
    
    if video_path:
        print("Official brand ad video found! Stripping original audio...")
        silent_video = strip_audio(video_path)
    else:
        print("No official brand ad video found. Initiating official product images slideshow fallback...")
        from app.scrapers.product_media_scraper import download_product_images
        image_paths = download_product_images(best_product['url'])
        if not image_paths:
            print("No official brand images found on product details page either. Aborting pipeline.")
            return
    
    # Phase 4: Script & Voiceover
    print("\n[5/7] Generating Script & Voiceover...")
    features = f"Trending at ₹{best_product['price']} on {best_product['platform']}."
    scripts = generate_scripts(best_product['title'], best_product['price'], features)
    if not scripts:
        print("Script generation failed.")
        return
        
    selected_script = scripts[0] # Pick the first variant
    print(f"Using Script Variant: {selected_script['variant_name']}")
    
    audio_path, sub_path = create_voiceover(selected_script['full_text'], filename="current_voiceover")
    
    final_video = compose_final_video(
        silent_video,
        audio_path,
        sub_path,
        product_name=best_product['title'],
        output_filename="final_render.mp4",
        image_paths=image_paths
    )
    if not final_video:
        print("Video rendering failed.")
        return
        
    # Phase 6: Publishing & Links
    print("\n[7/7] Generating Links and Publishing...")
    try:
        affiliate_link = generate_affiliate_link(best_product['url'], require_shortlink=True)
    except Exception as e:
        print(f"Affiliate short-link generation failed. Upload aborted: {e}")
        return

    seo_metadata = generate_seo_metadata(best_product['title'], selected_script['full_text'], affiliate_link)
    
    print("\n--- FINAL SEO METADATA ---")
    print(seo_metadata)
    print("--------------------------")
    
    # Upload — pass SRT for SEO caption indexing (mirrors ShortsAutomatorAIAgent)
    yt_url = upload_to_youtube(final_video, seo_metadata, srt_path=sub_path)
    upload_to_instagram(final_video, seo_metadata)
    
    print(f"\n=== PIPELINE COMPLETE! ===")
    if yt_url:
        print(f"YouTube Link: {yt_url}")


@app.post("/trigger")
def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    Endpoint to manually trigger the full pipeline in the background via API.
    """
    background_tasks.add_task(run_pipeline)
    return {"message": "Affiliate Pipeline triggered in background."}

if __name__ == "__main__":
    # If run directly via `python -m app.main`, execute the pipeline once synchronously
    run_pipeline()
    
    # To run as an API server instead, comment the above and uncomment below:
    # uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
