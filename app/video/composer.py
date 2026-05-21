"""
composer.py — Video Assembly for YouTube Shorts & Instagram Reels

Produces a 1080x1920 (9:16 vertical) output:
- Standard Video: Pillarboxes/crops the source video to fill the vertical frame
- Fallback Slideshow: Renders high-res marketing images into a seamless vertical slide show
- Audio Mixing: Downloads and mixes upbeat background music (SoundHelix) under the TTS voiceover
- Burns SRT subtitles if FFmpeg has libass; falls back gracefully
"""
import os
import subprocess
import ffmpeg
from app.config import WORKSPACE_DIR


def _get_ffmpeg_bin() -> str:
    """Resolve the best available FFmpeg binary path."""
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    local_bin    = os.path.join(project_root, "node_modules/@ffmpeg-installer/darwin-arm64/ffmpeg")
    if os.path.exists(local_bin):
        return local_bin
    return "ffmpeg"


def _has_filter(ffmpeg_bin: str, filter_name: str) -> bool:
    """Check if a specific FFmpeg filter is available."""
    try:
        result = subprocess.run([ffmpeg_bin, "-filters"], capture_output=True, text=True)
        return filter_name in result.stdout
    except Exception:
        return False


def get_media_duration(file_path: str) -> float:
    """Gets the duration of a media file using ffprobe."""
    ffmpeg_bin = _get_ffmpeg_bin()
    ffprobe_bin = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe_bin):
        ffprobe_bin = "ffprobe"
    
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting duration for {file_path}: {e}")
        return 40.0


def ensure_background_music() -> str:
    """Downloads a public domain upbeat instrumental track as background music if not present."""
    music_path = os.path.join(WORKSPACE_DIR, "background_music.mp3")
    if os.path.exists(music_path):
        return music_path
    
    url = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3"
    print(f"🎵 Downloading royalty-free background music: {url}...")
    try:
        import requests
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            with open(music_path, "wb") as f:
                f.write(resp.content)
            print("✅ Background music downloaded successfully.")
            return music_path
    except Exception as e:
        print(f"⚠️ Background music download failed: {e}. Fallback to voiceover only.")
    return None


def create_image_slide(image_path: str, duration: float, index: int) -> str:
    """
    Creates a temporary 1080x1920 vertical video slide of specified duration
    with blurred pillarbox background and centered foreground.
    """
    output_slide_path = os.path.join(WORKSPACE_DIR, f"temp_slide_{index}.mp4")
    ffmpeg_bin = _get_ffmpeg_bin()
    
    # Scale background to 1080x1920 with blur, scale foreground to fit width
    filter_complex = (
        "split[v1][v2];"
        "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=40:10[bg];"
        "[v2]scale=1080:-1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[vout]"
    )
    
    cmd = [
        ffmpeg_bin, "-y",
        "-loop", "1",
        "-t", f"{duration:.2f}",
        "-i", image_path,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "25",
        output_slide_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error creating slide {index}: {result.stderr[-300:]}")
        return None
    return output_slide_path


def concatenate_slides(slide_paths: list) -> str:
    """Stitches individual slide files into a single silent video using concat demuxer."""
    concat_txt_path = os.path.join(WORKSPACE_DIR, "slides.txt")
    output_video_path = os.path.join(WORKSPACE_DIR, "silent_slideshow.mp4")
    
    with open(concat_txt_path, "w", encoding="utf-8") as f:
        for path in slide_paths:
            # Writing absolute paths is fully supported by concat when using -safe 0
            f.write(f"file '{path}'\n")
            
    ffmpeg_bin = _get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_txt_path,
        "-c", "copy",
        output_video_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error concatenating slideshow: {result.stderr[-300:]}")
        return None
    return output_video_path


def select_best_clip_segment(video_path: str, product_name: str, audio_duration: float) -> float:
    """
    Intelligently selects the best start time in the downloaded video to trim a segment.
    """
    import json
    import re
    
    base_path = video_path.replace("_silent", "")
    info_path = os.path.splitext(base_path)[0] + ".info.json"
    
    title = ""
    description = ""
    duration = 0.0
    chapters = []
    
    if os.path.exists(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                title = meta.get("title", "")
                description = meta.get("description", "")
                duration = float(meta.get("duration", 0.0))
                chapters = meta.get("chapters", [])
        except Exception as e:
            print(f"Error reading info json: {e}")
            
    if duration <= 0:
        duration = get_media_duration(video_path)
        
    if duration <= audio_duration + 2.0:
        return 0.0
        
    if title or description or chapters:
        try:
            from google import genai
            from google.genai import types
            from app.config import GEMINI_API_KEY
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            chapters_summary = ""
            if chapters:
                chapters_summary = "\nChapters:\n" + "\n".join([
                    f"- {ch.get('start_time')}s to {ch.get('end_time')}s: {ch.get('title')}"
                    for ch in chapters
                ])
                
            prompt = f"""
            You are an expert AI video editor. Select the absolute best starting timestamp from a YouTube video to trim a segment of exactly {audio_duration:.1f} seconds.
            This segment will be used to make a high-conversion vertical YouTube Short for: "{product_name}".
            
            Video Metadata:
            - Title: {title}
            - Total Duration: {duration:.1f} seconds
            - Description: {description[:800]}
            {chapters_summary}
            
            Rules:
            1. The segment must be a SINGLE CONTINUOUS CLIP of exactly {audio_duration:.1f} seconds.
            2. It must represent a logical, engaging scene (e.g. product demo, feature showcase, unboxing).
            3. Avoid intro sequences, channel logos, sponsorships, or disclaimers.
            4. The start time MUST be between 0.0 and {duration - audio_duration - 2.0:.1f} seconds.
            
            Return ONLY a JSON object with:
            - "start_time": a float start time (e.g., 45.5).
            - "reason": short explanation.
            """
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            raw = response.text.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
            start_time = float(result.get("start_time", 0.0))
            
            if 0.0 <= start_time <= (duration - audio_duration - 1.0):
                return start_time
        except Exception as e:
            print(f"Gemini clip segment selection failed: {e}")
            
    fallback_start = duration * 0.15
    if fallback_start + audio_duration > duration:
        fallback_start = max(0.0, duration - audio_duration - 2.0)
    return fallback_start


def compose_final_video(silent_video_path, audio_path, subtitle_path, product_name=None, output_filename="final_render.mp4", image_paths=None):
    """
    Composes the final vertical Shorts video by:
    1. Compiling high-res images into a seamless slideshow if silent_video_path is None
    2. Merging voiceover mixed with background music
    3. Burning SRT subtitles
    """
    output_path = os.path.join(WORKSPACE_DIR, output_filename)
    ffmpeg_bin = _get_ffmpeg_bin()
    has_subtitles = _has_filter(ffmpeg_bin, "subtitles") and subtitle_path and os.path.exists(subtitle_path)
    
    # Check if we need to generate an image slideshow fallback
    is_slideshow = (silent_video_path is None)
    
    try:
        audio_duration = get_media_duration(audio_path)
        print(f"TTS Audio Duration: {audio_duration:.2f} seconds")

        if is_slideshow:
            if not image_paths:
                print("Error: Slideshow triggered but no images provided.")
                return None
            print(f"Initializing product image slideshowfallback ({len(image_paths)} images)...")
            
            slide_duration = audio_duration / len(image_paths)
            slide_clips = []
            for i, img in enumerate(image_paths):
                clip = create_image_slide(img, slide_duration, i)
                if clip:
                    slide_clips.append(clip)
            
            if not slide_clips:
                print("Error: Slide clip rendering failed.")
                return None
                
            silent_video_path = concatenate_slides(slide_clips)
            if not silent_video_path:
                print("Error: Slideshow concatenation failed.")
                return None
                
            start_time = 0.0
        else:
            start_time = select_best_clip_segment(silent_video_path, product_name or "a featured product", audio_duration)
            print(f"Selected Start Time from Video: {start_time:.2f} seconds")

        # ── Mixed Background Music Setup ──
        bg_music_path = ensure_background_music()
        srt_rel = f"workspace/{os.path.basename(subtitle_path)}" if subtitle_path else None

        # Build FFmpeg complex filters
        # v_pillarbox is the scale-and-blur filter for video stream 0:v
        v_pillarbox = (
            "split[v1][v2];"
            "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=40:10[bg];"
            "[v2]scale=1080:-1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        
        if bg_music_path and os.path.exists(bg_music_path):
            print("🎵 Background music mixed at 12% gain.")
            # amix merges voiceover (1:a) and bg music (2:a) with voice volume=1.0 and bg volume=0.12
            a_mix = "[2:a]volume=0.12[bg_vol]; [1:a][bg_vol]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            
            if has_subtitles:
                vf_complex = f"{v_pillarbox}[pv]; [pv]subtitles=filename={srt_rel}[vout]; {a_mix}"
            else:
                vf_complex = f"{v_pillarbox}[vout]; {a_mix}"
                
            cmd = [
                ffmpeg_bin, "-y",
                "-ss", f"{start_time:.2f}",
                "-t", f"{(audio_duration + 0.5):.2f}",
                "-i", silent_video_path,
                "-i", audio_path,
                "-i", bg_music_path,
                "-filter_complex", vf_complex,
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-shortest",
                output_path
            ]
        else:
            print("⚠️ Background music missing. Render with voiceover only.")
            if has_subtitles:
                vf_complex = f"{v_pillarbox}[pv]; [pv]subtitles=filename={srt_rel}[vout]"
            else:
                vf_complex = f"{v_pillarbox}[vout]"
                
            cmd = [
                ffmpeg_bin, "-y",
                "-ss", f"{start_time:.2f}",
                "-t", f"{(audio_duration + 0.5):.2f}",
                "-i", silent_video_path,
                "-i", audio_path,
                "-filter_complex", vf_complex,
                "-map", "[vout]",
                "-map", "1:a",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-shortest",
                output_path
            ]

        print(f"Rendering final Short: {output_path}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"FFmpeg render error:\n{result.stderr[-1000:]}")
            return None

        # Cleanup temporary files
        if is_slideshow:
            for i in range(len(image_paths) + 2):
                temp = os.path.join(WORKSPACE_DIR, f"temp_slide_{i}.mp4")
                if os.path.exists(temp):
                    try:
                        os.remove(temp)
                    except:
                        pass
            
            txt_path = os.path.join(WORKSPACE_DIR, "slides.txt")
            if os.path.exists(txt_path):
                try:
                    os.remove(txt_path)
                except:
                    pass
                    
            silent_slideshow = os.path.join(WORKSPACE_DIR, "silent_slideshow.mp4")
            if os.path.exists(silent_slideshow):
                try:
                    os.remove(silent_slideshow)
                except:
                    pass

        print(f"Final Shorts video rendered successfully: {output_path}")
        return output_path

    except Exception as e:
        print(f"Composition error: {e}")
        return None


if __name__ == "__main__":
    pass
