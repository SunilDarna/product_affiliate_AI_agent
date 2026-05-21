from google import genai
from google.genai import types
import json
import re
from app.config import GEMINI_API_KEY

def generate_seo_metadata(product_name, script_text, affiliate_link):
    """
    Uses Gemini LLM to generate SEO 2.0 optimized titles, descriptions,
    and hashtags for YouTube Shorts and Instagram Reels.

    Uses the same google.genai SDK as ShortsAutomatorAIAgent.
    Returns a dict with 'title', 'description', and 'hashtags'.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
You are an expert SEO and Social Media Manager specializing in YouTube Shorts and Instagram Reels in India.
Generate SEO 2.0 optimized metadata for a short video promoting this product:

Product: {product_name}
Video Script: {script_text}
Affiliate Link: {affiliate_link}

Output ONLY a valid JSON object with these exact keys:
- "title": A highly clickable, viral title under 60 characters (emojis allowed).
- "description": An engaging description. The first non-empty line MUST be the affiliate link exactly as provided, with no markdown, no label, and no punctuation around it. This keeps it clickable in YouTube.
- "hashtags": A string of 8-10 relevant trending hashtags (e.g., "#gadgets #india #tech").
"""

    try:
        print(f"Generating SEO metadata for: {product_name}")
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5)
        )
        raw = re.sub(r"```json|```", "", response.text.strip()).strip()
        metadata = json.loads(raw)
        metadata["affiliate_link"] = affiliate_link
        description = metadata.get("description", "")
        if affiliate_link not in description:
            description = f"{affiliate_link}\n\n{description}".strip()
        else:
            description = re.sub(re.escape(affiliate_link), "", description, count=1).strip()
            description = f"{affiliate_link}\n\n{description}".strip()
        metadata["description"] = description
        return metadata

    except Exception as e:
        print(f"Error generating SEO metadata: {e}")
        # Fallback metadata — keeps pipeline running
        return {
            "title": f"Must Buy: {product_name[:40]} 🚀",
            "description": f"{affiliate_link}\n\nCheck this out!\n\n{script_text[:300]}\n\nSubscribe for daily deals!",
            "hashtags": "#tech #gadgets #india #deals #trending #musthave #viral #shorts #reels #buy",
            "affiliate_link": affiliate_link,
        }

if __name__ == "__main__":
    res = generate_seo_metadata(
        "Noise Smartwatch",
        "This is the best smartwatch under 2000!",
        "https://amzn.to/12345"
    )
    print(res)
