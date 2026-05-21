"""
thumbnail.py — Gemini/Kimi thumbnail generation and first-frame injection.

The flow is:
1. Extract a few representative frames from the rendered Short.
2. Send those frames plus product/script/trend context to the user's logged-in Gemini
   browser session through Kimi WebBridge.
3. Save the generated image locally.
4. Prepend it to the final video as a short first-frame segment so YouTube can use it
   when manually selecting a thumbnail frame.
"""
import base64
import asyncio
import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

import requests
from playwright.async_api import async_playwright

from app.config import WORKSPACE_DIR
from app.video.composer import _get_ffmpeg_bin, get_media_duration


KIMI_BASE_URL = "http://127.0.0.1:10086"
KIMI_COMMAND_URL = f"{KIMI_BASE_URL}/command"
KIMI_SESSION = "gemini-thumbnail"
GEMINI_URL = "https://gemini.google.com/app"


def _save_json(name: str, data: Any) -> None:
    try:
        path = os.path.join(WORKSPACE_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Saved thumbnail diagnostic: {path}")
    except Exception as exc:
        print(f"Could not save thumbnail diagnostic {name}: {exc}")


def _kimi_command(action: str, args: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    payload = {"action": action, "args": args or {}, "session": KIMI_SESSION}
    response = requests.post(KIMI_COMMAND_URL, json=payload, timeout=timeout)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    body["_http_status"] = response.status_code
    return body


def _command_ok(result: Dict[str, Any]) -> bool:
    return bool(result.get("ok") or result.get("success"))


def _command_value(result: Dict[str, Any]) -> Any:
    if isinstance(result.get("data"), dict) and "value" in result["data"]:
        return result["data"]["value"]
    if "value" in result:
        return result["value"]
    if "result" in result:
        return result["result"]
    return result


def _kimi_ready() -> bool:
    try:
        response = requests.get(f"{KIMI_BASE_URL}/status", timeout=2)
        if response.status_code != 200:
            print(f"Kimi WebBridge status HTTP {response.status_code}.")
            return False
        status = response.json()
        if status.get("running") and status.get("extension_connected"):
            return True
        print(f"Kimi WebBridge is not ready for Gemini thumbnail generation: {status}")
        return False
    except Exception as exc:
        print(f"Kimi WebBridge is not reachable for Gemini thumbnail generation: {exc}")
        return False


def extract_thumbnail_frames(video_path: str, count: int = 2) -> List[str]:
    """Extracts the most visually useful 1080x1920 JPEG frames from the rendered video."""
    if not video_path or not os.path.exists(video_path):
        return []

    frames_dir = os.path.join(WORKSPACE_DIR, "thumbnail_frames")
    os.makedirs(frames_dir, exist_ok=True)
    for name in os.listdir(frames_dir):
        if name.startswith("frame_") or name.startswith("candidate_"):
            try:
                os.remove(os.path.join(frames_dir, name))
            except Exception:
                pass

    duration = max(1.0, get_media_duration(video_path))
    candidate_count = 14
    if duration <= 5:
        timestamps = [duration * 0.25, duration * 0.5, duration * 0.75]
    else:
        timestamps = [1.5 + ((duration - 3.0) * i / max(1, candidate_count - 1)) for i in range(candidate_count)]

    ffmpeg_bin = _get_ffmpeg_bin()
    candidates = []
    for index, timestamp in enumerate(timestamps):
        output = os.path.join(frames_dir, f"candidate_{index}.jpg")
        cmd = [
            ffmpeg_bin, "-y",
            "-ss", f"{timestamp:.2f}",
            "-i", video_path,
            "-frames:v", "1",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-q:v", "2",
            output,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(output):
            candidates.append((timestamp, output))
        else:
            print(f"Thumbnail frame extraction failed at {timestamp:.2f}s: {result.stderr[-300:]}")

    selected = _select_best_frame_candidates(candidates, count=count)
    print(f"Extracted {len(selected)} meaningful thumbnail reference frame(s).")
    return selected


def _score_frame(frame_path: str) -> float:
    try:
        from PIL import Image, ImageStat
    except Exception:
        return 1.0

    try:
        img = Image.open(frame_path).convert("RGB").resize((180, 320))
        gray = img.convert("L")
        stat = ImageStat.Stat(gray)
        brightness = stat.mean[0]
        contrast = stat.stddev[0]

        # Simple edge energy without OpenCV: compare neighboring grayscale pixels.
        pixels = gray.load()
        edge_sum = 0
        edge_count = 0
        for y in range(0, gray.height - 1, 4):
            for x in range(0, gray.width - 1, 4):
                edge_sum += abs(pixels[x, y] - pixels[x + 1, y]) + abs(pixels[x, y] - pixels[x, y + 1])
                edge_count += 2
        edge_energy = edge_sum / max(1, edge_count)

        sat = ImageStat.Stat(img.convert("HSV")).mean[1]
        brightness_penalty = abs(brightness - 135) * 0.15
        too_flat_penalty = 30 if contrast < 18 else 0
        return (contrast * 1.5) + (edge_energy * 2.0) + (sat * 0.25) - brightness_penalty - too_flat_penalty
    except Exception:
        return 1.0


def _select_best_frame_candidates(candidates: List[tuple], count: int = 2) -> List[str]:
    if not candidates:
        return []

    scored = []
    for timestamp, path in candidates:
        scored.append((_score_frame(path), timestamp, path))
    scored.sort(reverse=True)

    selected = []
    min_gap = 2.0
    for score, timestamp, path in scored:
        if all(abs(timestamp - chosen_ts) >= min_gap for chosen_ts, _ in selected):
            selected.append((timestamp, path))
        if len(selected) >= count:
            break

    if len(selected) < count:
        for _, timestamp, path in scored:
            if path not in [p for _, p in selected]:
                selected.append((timestamp, path))
            if len(selected) >= count:
                break

    frame_paths = []
    for index, (_, path) in enumerate(selected[:count]):
        final_path = os.path.join(os.path.dirname(path), f"frame_{index}.jpg")
        try:
            os.replace(path, final_path)
        except Exception:
            final_path = path
        frame_paths.append(final_path)

    for _, path in candidates:
        if os.path.exists(path) and path not in frame_paths:
            try:
                os.remove(path)
            except Exception:
                pass

    return frame_paths


def _build_thumbnail_prompt(product: Dict[str, Any], script_text: str, trends: List[str]) -> str:
    title = product.get("title", "Featured product")
    price = product.get("price", "")
    platform = product.get("platform", "Amazon India")
    trend_text = ", ".join(trends[:5]) if trends else "viral shopping, content creator tools, India deals"

    return f"""
Create a viral YouTube Shorts thumbnail image in 9:16 vertical ratio using the attached product/video frames as visual reference.

Product:
- Name: {title}
- Price: ₹{price}
- Platform: {platform}

Current trend signals:
{trend_text}

Video story/context:
{script_text[:900]}

Thumbnail requirements:
- STRICT PRODUCT MATCH RULE: Create the thumbnail for exactly this product only: "{title}".
- Use only the uploaded reference frames for product appearance. Do not reuse any previous Gemini image or product from the chat history.
- If the frame shows a light, thumbnail must show a light. If it shows a microphone, thumbnail must show a microphone. Never substitute another product category.
- Must be a premium, high-CTR YouTube Shorts thumbnail for Indian viewers.
- Same vertical 9:16 ratio as the video, optimized for 1080x1920.
- Make the product unmistakably visible and visually attractive.
- Use bold readable text, maximum 3 to 5 words.
- Use a clear hook based on the problem/benefit, not a spammy sales pitch.
- Use energetic contrast, face/hand/product emphasis if useful, and clean composition.
- Avoid fake discounts, fake ratings, misleading before/after claims, marketplace logos, Amazon logos, watermarks, unrelated brand names, or extra logos.
- Do not invent accessories, labels, or packaging from other brands. Keep visual details consistent with the uploaded product frames.
- Do not include URLs, QR codes, affiliate text, watermarks, or tiny unreadable text.

Generate one final thumbnail image only.
""".strip()


def _download_generated_image_from_gemini(output_path: str, baseline_images: Optional[List[str]] = None) -> bool:
    """Finds the most recent generated image in Gemini and downloads it from the page context."""
    baseline_json = json.dumps(baseline_images or [])
    js = """
    (async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      const baseline = new Set(__BASELINE_IMAGES__);
      const imageKey = img => img.currentSrc || img.src || '';
      for (let attempt = 0; attempt < 90; attempt++) {
        const images = [...document.images]
          .filter(img => img.naturalWidth >= 256 && img.naturalHeight >= 256)
          .filter(img => {
            const alt = (img.alt || '').toLowerCase();
            const src = imageKey(img);
            return src && !baseline.has(src) && !alt.includes('user') && !alt.includes('uploaded') && !src.includes('googleusercontent.com/ogw');
          });
        const img = images.reverse().find(candidate => (candidate.alt || '').toLowerCase().includes('ai generated')) || images[0];
        if (img) {
          const src = imageKey(img);
          try {
            let data = '';
            try {
              const canvas = document.createElement('canvas');
              canvas.width = img.naturalWidth;
              canvas.height = img.naturalHeight;
              const ctx = canvas.getContext('2d');
              ctx.drawImage(img, 0, 0);
              data = canvas.toDataURL('image/png');
            } catch (canvasError) {
              const response = await fetch(src);
              const blob = await response.blob();
              const reader = new FileReader();
              data = await new Promise((resolve, reject) => {
                reader.onloadend = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
              });
            }
            return {success: true, dataUrl: data, width: img.naturalWidth, height: img.naturalHeight, src};
          } catch (error) {
            return {success: false, error: String(error), src};
          }
        }
        await sleep(2000);
      }
      return {success: false, error: 'No newly generated image found in Gemini response', baselineCount: baseline.size, currentImageCount: document.images.length};
    })()
    """.replace("__BASELINE_IMAGES__", baseline_json)

    result = _kimi_command("evaluate", {"code": js}, timeout=210)
    value = _command_value(result)
    if not (isinstance(value, dict) and value.get("success") and value.get("dataUrl")):
        _save_json("thumbnail_gemini_download_diagnostic.json", {"result": result, "value": value})
        return False

    match = re.match(r"data:image/[^;]+;base64,(.+)$", value["dataUrl"])
    if not match:
        _save_json("thumbnail_gemini_download_diagnostic.json", {"error": "Generated image was not a data URL", "value": value})
        return False

    with open(output_path, "wb") as f:
        f.write(base64.b64decode(match.group(1)))

    print(f"Downloaded Gemini thumbnail image: {output_path} ({value.get('width')}x{value.get('height')})")
    return True


async def _generate_thumbnail_with_gemini_cdp(product: Dict[str, Any], script_text: str, trends: List[str], frame_paths: List[str]) -> Optional[str]:
    """
    Fallback for Gemini file upload when Kimi WebBridge reports DevTools
    "Not allowed" on Gemini's hidden file input. This still uses the user's
    logged-in Chrome/Gemini session.
    """
    prompt = _build_thumbnail_prompt(product, script_text, trends)
    output_path = os.path.join(WORKSPACE_DIR, "generated_thumbnail.png")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = None
            for candidate in context.pages:
                if candidate.url.startswith("https://gemini.google.com/app"):
                    page = candidate
                    break
            if page is None:
                page = await context.new_page()
                await page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=45000)

            await page.bring_to_front()
            await page.wait_for_timeout(2000)

            try:
                new_chat = page.get_by_role("link", name=re.compile("new chat", re.I)).first
                await new_chat.click(timeout=5000)
                await page.wait_for_timeout(3000)
            except Exception:
                await page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)

            baseline_images = await page.evaluate("""
            () => [...document.images]
              .map(img => img.currentSrc || img.src || '')
              .filter(Boolean)
            """)
            started_at_ms = int(time.time() * 1000)

            await page.evaluate("""
            (() => {
              const click = el => { if (el) el.click(); return !!el; };
              const buttons = [...document.querySelectorAll('button, [role="button"], [role="menuitem"], [role="menuitemcheckbox"]')];
              const tools = buttons.find(btn => /upload and tools/i.test(btn.getAttribute('aria-label') || btn.textContent || ''));
              click(tools);
              setTimeout(() => {
                const all = [...document.querySelectorAll('button, [role="menuitem"], [role="menuitemcheckbox"]')];
                const createImage = all.find(btn => /create image/i.test(btn.textContent || btn.getAttribute('aria-label') || ''));
                click(createImage);
              }, 500);
            })()
            """)
            await page.wait_for_timeout(1500)

            await page.evaluate("""
            (() => {
              const click = el => { if (el) el.click(); return !!el; };
              const buttons = [...document.querySelectorAll('button, [role="button"], [role="menuitem"]')];
              const tools = buttons.find(btn => /upload and tools/i.test(btn.getAttribute('aria-label') || btn.textContent || ''));
              click(tools);
              setTimeout(() => {
                const all = [...document.querySelectorAll('button, [role="menuitem"]')];
                const uploadFiles = all.find(btn => /upload files/i.test(btn.textContent || btn.getAttribute('aria-label') || ''));
                click(uploadFiles);
              }, 500);
            })()
            """)
            await page.wait_for_timeout(1500)

            await page.locator("input[type=file]").last.set_input_files(frame_paths)
            await page.wait_for_timeout(3000)

            textbox = page.get_by_role("textbox", name="Enter a prompt for Gemini")
            await textbox.fill(prompt, timeout=15000)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            await page.evaluate("""
            (() => {
              const buttons = [...document.querySelectorAll('button')];
              const send = buttons.find(btn => /send message/i.test(btn.getAttribute('aria-label') || ''));
              if (send) send.click();
              return {clicked: !!send};
            })()
            """)

            download_result = await page.evaluate("""
            async ({ baselineImages, startedAtMs }) => {
              const sleep = ms => new Promise(r => setTimeout(r, ms));
              const baseline = new Set(baselineImages || []);
              const imageKey = img => img.currentSrc || img.src || '';
              const usable = img => {
                const alt = (img.alt || '').toLowerCase();
                const src = imageKey(img);
                if (!src || baseline.has(src)) return false;
                if (img.naturalWidth < 256 || img.naturalHeight < 256) return false;
                if (alt.includes('uploaded') || alt.includes('user')) return false;
                if (src.includes('googleusercontent.com/ogw')) return false;
                return true;
              };
              for (let i = 0; i < 90; i++) {
                const images = [...document.images]
                  .filter(usable)
                  .filter(img => {
                    const rect = img.getBoundingClientRect();
                    return rect.width > 120 && rect.height > 120;
                  });
                const generated = images.reverse().find(img => (img.alt || '').toLowerCase().includes('ai generated')) || images[0];
                if (generated) {
                  try {
                    const canvas = document.createElement('canvas');
                    canvas.width = generated.naturalWidth;
                    canvas.height = generated.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(generated, 0, 0);
                    return {
                      success: true,
                      dataUrl: canvas.toDataURL('image/png'),
                      width: generated.naturalWidth,
                      height: generated.naturalHeight,
                      src: imageKey(generated),
                      alt: generated.alt || '',
                      newImageCount: images.length,
                      startedAtMs
                    };
                  } catch (canvasError) {
                    const response = await fetch(generated.currentSrc || generated.src);
                    const blob = await response.blob();
                    const reader = new FileReader();
                    const dataUrl = await new Promise((resolve, reject) => {
                      reader.onloadend = () => resolve(reader.result);
                      reader.onerror = reject;
                      reader.readAsDataURL(blob);
                    });
                    return {
                      success: true,
                      dataUrl,
                      width: generated.naturalWidth,
                      height: generated.naturalHeight,
                      src: imageKey(generated),
                      alt: generated.alt || '',
                      newImageCount: images.length,
                      startedAtMs
                    };
                  }
                }
                await sleep(2000);
              }
              return {
                success: false,
                error: 'No newly generated image found in Gemini response',
                baselineCount: baseline.size,
                currentImageCount: document.images.length,
                startedAtMs
              };
            }
            """, {"baselineImages": baseline_images, "startedAtMs": started_at_ms})

            if not (isinstance(download_result, dict) and download_result.get("success") and download_result.get("dataUrl")):
                _save_json("thumbnail_gemini_cdp_download_diagnostic.json", download_result)
                return None

            match = re.match(r"data:image/[^;]+;base64,(.+)$", download_result["dataUrl"])
            if not match:
                _save_json("thumbnail_gemini_cdp_download_diagnostic.json", {"error": "Generated image was not a data URL", "download_result": download_result})
                return None

            with open(output_path, "wb") as f:
                f.write(base64.b64decode(match.group(1)))

            _save_json("thumbnail_generation_manifest.json", {
                "product_title": product.get("title"),
                "frame_paths": frame_paths,
                "selected_image": {
                    "width": download_result.get("width"),
                    "height": download_result.get("height"),
                    "alt": download_result.get("alt"),
                    "src": download_result.get("src"),
                    "new_image_count": download_result.get("newImageCount"),
                },
                "started_at_ms": started_at_ms,
            })
            print(f"Downloaded new Gemini thumbnail image via Chrome CDP: {output_path}")
            return output_path
    except Exception as exc:
        _save_json("thumbnail_gemini_cdp_exception.json", {"error": str(exc)})
        print(f"Gemini thumbnail CDP fallback failed: {exc}")
        return None


def generate_thumbnail_with_gemini(product: Dict[str, Any], script_text: str, trends: List[str], frame_paths: List[str]) -> Optional[str]:
    """
    Uses Kimi WebBridge to control the user's logged-in Gemini session and generate
    a viral thumbnail from product context plus video frames.
    """
    if not frame_paths:
        print("Skipping Gemini thumbnail generation: no reference frames were extracted.")
        return None

    if not _kimi_ready():
        print("Kimi WebBridge is not ready. Trying Chrome CDP fallback for Gemini thumbnail generation...")
        return asyncio.run(_generate_thumbnail_with_gemini_cdp(product, script_text, trends, frame_paths))

    prompt = _build_thumbnail_prompt(product, script_text, trends)
    output_path = os.path.join(WORKSPACE_DIR, "generated_thumbnail.png")

    try:
        nav = _kimi_command("navigate", {"url": GEMINI_URL, "newTab": True, "group_title": "Thumbnail Gemini"}, timeout=30)
        if not _command_ok(nav):
            _save_json("thumbnail_gemini_nav_diagnostic.json", nav)
            print("Gemini navigation via Kimi failed. Trying Chrome CDP fallback...")
            return asyncio.run(_generate_thumbnail_with_gemini_cdp(product, script_text, trends, frame_paths))

        time.sleep(7)

        _kimi_command("evaluate", {
            "code": """
            (() => {
              const links = [...document.querySelectorAll('a')];
              const newChat = links.find(link => /new chat/i.test(link.textContent || link.getAttribute('aria-label') || ''));
              if (newChat) {
                newChat.click();
                return {clicked: true};
              }
              return {clicked: false};
            })()
            """
        }, timeout=10)
        time.sleep(3)

        baseline_result = _kimi_command("evaluate", {
            "code": """
            (() => [...document.images]
              .map(img => img.currentSrc || img.src || '')
              .filter(Boolean))()
            """
        }, timeout=10)
        baseline_value = _command_value(baseline_result)
        baseline_images = baseline_value if isinstance(baseline_value, list) else []

        # Put Gemini in image-generation mode when the current UI exposes it.
        _kimi_command("evaluate", {
            "code": """
            (() => {
              const click = el => {
                if (!el) return false;
                el.click();
                return true;
              };
              const buttons = [...document.querySelectorAll('button, [role="button"], [role="menuitem"], [role="menuitemcheckbox"]')];
              const tools = buttons.find(btn => /upload and tools/i.test(btn.getAttribute('aria-label') || btn.textContent || ''));
              click(tools);
              setTimeout(() => {
                const all = [...document.querySelectorAll('button, [role="menuitem"], [role="menuitemcheckbox"]')];
                const createImage = all.find(btn => /create image/i.test(btn.textContent || btn.getAttribute('aria-label') || ''));
                click(createImage);
              }, 500);
              return {clickedTools: !!tools};
            })()
            """
        }, timeout=10)
        time.sleep(2)

        # Gemini creates the hidden file input only after Upload and tools -> Upload files.
        _kimi_command("evaluate", {
            "code": """
            (() => {
              const click = el => {
                if (!el) return false;
                el.click();
                return true;
              };
              const buttons = [...document.querySelectorAll('button, [role="button"], [role="menuitem"]')];
              const tools = buttons.find(btn => /upload and tools/i.test(btn.getAttribute('aria-label') || btn.textContent || ''));
              click(tools);
              setTimeout(() => {
                const all = [...document.querySelectorAll('button, [role="menuitem"]')];
                const uploadFiles = all.find(btn => /upload files/i.test(btn.textContent || btn.getAttribute('aria-label') || ''));
                click(uploadFiles);
              }, 500);
              return {clickedTools: !!tools};
            })()
            """
        }, timeout=10)
        time.sleep(2)

        upload = _kimi_command("upload", {"selector": "input[type='file']", "files": frame_paths}, timeout=60)

        if not _command_ok(upload):
            _save_json("thumbnail_gemini_upload_diagnostic.json", upload)
            print("Gemini thumbnail upload via Kimi failed. Trying Chrome CDP fallback...")
            return asyncio.run(_generate_thumbnail_with_gemini_cdp(product, script_text, trends, frame_paths))

        fill_selector = "rich-textarea [contenteditable='true'], div[contenteditable='true'], textarea"
        fill = _kimi_command("fill", {"selector": fill_selector, "value": prompt}, timeout=30)
        if not _command_ok(fill):
            _save_json("thumbnail_gemini_fill_diagnostic.json", fill)
            print("Gemini thumbnail prompt fill via Kimi failed. Trying Chrome CDP fallback...")
            return asyncio.run(_generate_thumbnail_with_gemini_cdp(product, script_text, trends, frame_paths))

        submit = _kimi_command("evaluate", {
            "code": """
            (() => {
              const buttons = [...document.querySelectorAll('button, [role="button"]')];
              const submit = buttons.reverse().find(btn => {
                const label = (btn.getAttribute('aria-label') || btn.textContent || '').toLowerCase();
                return /send|submit|run|generate/.test(label) && !btn.disabled;
              });
              if (submit) {
                submit.click();
                return {success: true, label: submit.getAttribute('aria-label') || submit.textContent || ''};
              }
              const active = document.activeElement;
              if (active) {
                active.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', metaKey: true, bubbles: true}));
              }
              return {success: false, error: 'Submit button not found'};
            })()
            """
        }, timeout=20)

        if not _command_ok(submit):
            _save_json("thumbnail_gemini_submit_diagnostic.json", submit)

        if _download_generated_image_from_gemini(output_path, baseline_images=baseline_images):
            return output_path
        print("Gemini thumbnail download via Kimi did not find a new image. Trying Chrome CDP fallback...")
        return asyncio.run(_generate_thumbnail_with_gemini_cdp(product, script_text, trends, frame_paths))
    except Exception as exc:
        _save_json("thumbnail_gemini_exception.json", {"error": str(exc)})
        print(f"Gemini thumbnail generation failed: {exc}")

    return None


def prepend_thumbnail_to_video(video_path: str, thumbnail_path: str, output_filename: str = "final_render_with_thumbnail.mp4", hold_seconds: float = 1.0) -> Optional[str]:
    """Prepends the generated thumbnail as the first visible segment of the Short."""
    if not video_path or not os.path.exists(video_path):
        print("Cannot prepend thumbnail: final video does not exist.")
        return None
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print("Cannot prepend thumbnail: thumbnail image does not exist.")
        return None

    ffmpeg_bin = _get_ffmpeg_bin()
    thumbnail_clip = os.path.join(WORKSPACE_DIR, "thumbnail_intro.mp4")
    output_path = os.path.join(WORKSPACE_DIR, output_filename)

    create_intro_cmd = [
        ffmpeg_bin, "-y",
        "-loop", "1",
        "-t", f"{hold_seconds:.2f}",
        "-i", thumbnail_path,
        "-f", "lavfi",
        "-t", f"{hold_seconds:.2f}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-r", "25",
        "-pix_fmt", "yuv420p",
        "-shortest",
        thumbnail_clip,
    ]
    result = subprocess.run(create_intro_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Thumbnail intro render failed: {result.stderr[-500:]}")
        return None

    concat_cmd = [
        ffmpeg_bin, "-y",
        "-i", thumbnail_clip,
        "-i", video_path,
        "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Thumbnail prepend failed: {result.stderr[-800:]}")
        return None

    print(f"Prepended thumbnail first frame video: {output_path}")
    return output_path


def add_ai_thumbnail_first_frame(video_path: str, product: Dict[str, Any], script_text: str, trends: List[str]) -> str:
    """
    Best-effort thumbnail enhancement. If Gemini generation fails, the original video
    is returned so the monetized pipeline can continue.
    """
    print("\n[6/8] Generating viral thumbnail first frame via Gemini/Kimi...")
    frames = extract_thumbnail_frames(video_path, count=2)
    thumbnail_path = generate_thumbnail_with_gemini(product, script_text, trends, frames)
    if not thumbnail_path:
        print("Thumbnail generation skipped/failed. Continuing with original final video.")
        return video_path

    enhanced_video = prepend_thumbnail_to_video(video_path, thumbnail_path)
    return enhanced_video or video_path
