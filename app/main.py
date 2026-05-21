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
from app.video.thumbnail import add_ai_thumbnail_first_frame
from app.publish.link_generator import generate_affiliate_link, validate_amazon_shortlink
from app.publish.seo_generator import generate_seo_metadata
from app.publish.uploader import upload_to_youtube, upload_to_instagram
from app.utils.preflight import run_preflight
from app.utils.retry import retry_stage
from app.utils.run_manifest import RunManifest

from app.config import YOUTUBE_CHANNEL_HANDLE

# New performance learning loop imports
from app.scrapers.youtube_studio_scraper import scrape_youtube_studio_analytics
from app.analytics.performance_analyzer import run_performance_analysis

app = FastAPI(title="Product Affiliate AI Agent", description="Autonomous pipeline for affiliate shorts")

def run_pipeline():
    print("\n=== STARTING PRODUCT AFFILIATE PIPELINE ===")
    manifest = RunManifest()
    
    try:
        print("\n[0/8] Running automation preflight...")
        preflight = run_preflight(strict=True)
        manifest.set_artifact("preflight", preflight)

        # Initialize the SQLite tracking database for conflict prevention
        from app.utils.db_tracker import init_db, record_product
        init_db()
        
        # Phase 1: YouTube Performance Analysis & Learning Loop
        print(f"\n[1/8] Scraping YouTube Studio Analytics for {YOUTUBE_CHANNEL_HANDLE} (Active CDP Session)...")
        try:
            raw_analytics = asyncio.run(scrape_youtube_studio_analytics(YOUTUBE_CHANNEL_HANDLE))
            if raw_analytics and raw_analytics.get("videos"):
                print(f"Found {len(raw_analytics['videos'])} video(s) uploaded in the past 15 days. Running performance synthesis...")
                learnings = run_performance_analysis(raw_analytics)
                if learnings:
                    print("Performance analysis complete. Channel learnings saved successfully.")
                    manifest.set_artifact("learnings_saved", True)
            else:
                print("No videos found from the past 15 days on the channel. Skipping performance analysis and proceeding with robust base LLM product selection.")
        except Exception as e:
            print(f"Phase 1 Performance Loop failed (Pipeline continuing): {e}")
            manifest.set_artifact("performance_loop_warning", str(e))
        
        # Phase 2: Trend Discovery & Scraping
        print("\n[2/8] Discovering Trends...")
        trends = retry_stage("trend_discovery", get_trending_topics_india, attempts=2, manifest=manifest)
        manifest.set_artifact("trends", trends)
        print(f"Discovered Trends: {trends}")
        
        print("\n[3/8] Scraping Affiliate Platforms...")
        best_product = retry_stage("product_selection", lambda: get_best_product(trends), attempts=2, manifest=manifest)
        if not best_product:
            raise RuntimeError("No suitable high-commission product found")
        manifest.set_artifact("product", best_product)
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
        print("\n[4/8] Sourcing Video Clip...")
        manifest.stage_started("video_sourcing", {"allows_image_fallback": True})
        video_path = search_and_download_ad(best_product['title'])
        manifest.stage_completed("video_sourcing", {"video_path": video_path})
        manifest.set_artifact("raw_video", video_path)
        
        image_paths = None
        silent_video = None
        
        if video_path:
            print("Official brand ad video found! Stripping original audio...")
            silent_video = retry_stage("strip_audio", lambda: strip_audio(video_path), attempts=2, manifest=manifest)
        else:
            print("No official brand ad video found. Initiating official product images slideshow fallback...")
            from app.scrapers.product_media_scraper import download_product_images
            image_paths = retry_stage("product_image_fallback", lambda: download_product_images(best_product['url']), attempts=2, manifest=manifest)
            if not image_paths:
                raise RuntimeError("No official brand images found on product page")
        
        # Phase 4: Script & Voiceover
        print("\n[5/8] Generating Script & Voiceover...")
        features = f"Trending at ₹{best_product['price']} on {best_product['platform']}."
        scripts = retry_stage(
            "script_generation",
            lambda: generate_scripts(best_product['title'], best_product['price'], features),
            attempts=2,
            manifest=manifest,
        )
        if not scripts:
            raise RuntimeError("Script generation failed")
            
        selected_script = scripts[0] # Pick the first variant
        manifest.set_artifact("selected_script", selected_script)
        print(f"Using Script Variant: {selected_script['variant_name']}")
        
        audio_path, sub_path = retry_stage(
            "voiceover",
            lambda: create_voiceover(selected_script['full_text'], filename="current_voiceover"),
            attempts=2,
            manifest=manifest,
        )
        manifest.set_artifact("audio_path", audio_path)
        manifest.set_artifact("subtitle_path", sub_path)
        
        final_video = retry_stage(
            "video_render",
            lambda: compose_final_video(
                silent_video,
                audio_path,
                sub_path,
                product_name=best_product['title'],
                output_filename="final_render.mp4",
                image_paths=image_paths
            ),
            attempts=2,
            manifest=manifest,
        )
        manifest.set_artifact("final_video", final_video)

        final_video = retry_stage(
            "thumbnail_generation",
            lambda: add_ai_thumbnail_first_frame(
                final_video,
                product=best_product,
                script_text=selected_script['full_text'],
                trends=trends,
                strict=True,
            ),
            attempts=2,
            delay_seconds=8,
            manifest=manifest,
        )
        manifest.set_artifact("final_video_with_thumbnail", final_video)
            
        # Phase 6: Publishing & Links
        print("\n[7/8] Generating Links and Publishing...")
        affiliate_link = retry_stage(
            "affiliate_shortlink",
            lambda: generate_affiliate_link(best_product['url'], require_shortlink=True),
            attempts=3,
            delay_seconds=8,
            manifest=manifest,
        )
        if not validate_amazon_shortlink(affiliate_link):
            raise RuntimeError(f"Generated affiliate link is not an Amazon shortlink: {affiliate_link}")
        manifest.set_artifact("affiliate_shortlink", affiliate_link)

        seo_metadata = retry_stage(
            "seo_metadata",
            lambda: generate_seo_metadata(best_product['title'], selected_script['full_text'], affiliate_link),
            attempts=2,
            manifest=manifest,
        )
        
        print("\n--- FINAL SEO METADATA ---")
        print(seo_metadata)
        print("--------------------------")
        
        # Upload — pass SRT for SEO caption indexing (mirrors ShortsAutomatorAIAgent)
        yt_url = retry_stage(
            "youtube_upload",
            lambda: upload_to_youtube(final_video, seo_metadata, srt_path=sub_path),
            attempts=2,
            delay_seconds=15,
            manifest=manifest,
        )
        manifest.set_artifact("youtube_url", yt_url)
        upload_to_instagram(final_video, seo_metadata)
        
        print(f"\n=== PIPELINE COMPLETE! ===")
        if yt_url:
            print(f"YouTube Link: {yt_url}")
        manifest.finish("completed")
    except Exception as exc:
        manifest.stage_failed("pipeline", exc)
        manifest.finish("failed")
        print(f"\n=== PIPELINE FAILED ===\n{exc}")
        raise


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
