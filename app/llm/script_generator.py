from google import genai
from google.genai import types
import json
import re
from app.config import GEMINI_API_KEY

def generate_scripts(product_name, product_price, product_features=""):
    """
    Uses Google Gemini to generate 4-5 engaging, hook-driven script variants
    for a short-form video (YouTube Shorts / Instagram Reels).

    Uses the same google.genai SDK and model as ShortsAutomatorAIAgent.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
You are an expert viral content writer specializing in product promotion for YouTube Shorts and Instagram Reels targeting the Indian audience.

Generate 4 engaging, hook-driven script variants to promote this product:
- Product: {product_name}
- Price: ₹{product_price}
- Features: {product_features}

Each script variant must:
1. Be 30-55 seconds when spoken aloud at a normal pace (approximately 80-130 words).
2. Start with a strong, scroll-stopping HOOK (first 3 seconds).
3. Have a clear BODY explaining the value/features.
4. End with a strong CALL TO ACTION directing viewers to the link in bio/description.
5. Use energetic, conversational English suitable for Indian audiences.

Output ONLY a valid JSON array of objects. Each object must have these exact keys:
- "variant_name": short label (e.g., "Hype", "Value", "Curiosity", "Problem-Solution")
- "hook": the opening hook sentence only
- "body": the middle section text only
- "call_to_action": the closing CTA sentence only
- "full_text": the complete script as one paragraph
"""

    try:
        print(f"Generating scripts for: {product_name}")
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )

        raw = response.text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()

        scripts = json.loads(raw)
        print(f"Successfully generated {len(scripts)} script variants.")
        return scripts

    except Exception as e:
        print(f"Error generating scripts: {e}")
        # Robust fallback — pipeline continues even if LLM fails
        return [
            {
                "variant_name": "Fallback Hype",
                "hook": "Stop scrolling right now!",
                "body": f"This {product_name} is the best thing you can buy today for just ₹{product_price}. It's trending all over India and selling out fast.",
                "call_to_action": "Check the link in the description to grab yours before it's gone!",
                "full_text": f"Stop scrolling right now! This {product_name} is the best thing you can buy today for just ₹{product_price}. It's trending all over India and selling out fast. Check the link in the description to grab yours before it's gone!"
            }
        ]

if __name__ == "__main__":
    results = generate_scripts("Noise Smartwatch", 2499, "10-day battery, SpO2, 1.8-inch AMOLED display")
    for r in results:
        print(f"\n--- {r['variant_name']} ---")
        print(r['full_text'])
