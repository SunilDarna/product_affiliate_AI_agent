import os
import json
import re
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, WORKSPACE_DIR

LEARNINGS_PATH = os.path.join(WORKSPACE_DIR, "learnings.json")

def load_existing_learnings():
    """Loads any historical learnings if they exist, to allow incremental optimization."""
    if os.path.exists(LEARNINGS_PATH):
        try:
            with open(LEARNINGS_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read existing learnings: {e}")
    return {}

def save_learnings(learnings):
    """Saves the synthesized learnings to the workspace directory."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(LEARNINGS_PATH), exist_ok=True)
        with open(LEARNINGS_PATH, 'w') as f:
            json.dump(learnings, f, indent=4)
        print(f"Successfully saved performance learnings to: {LEARNINGS_PATH}")
    except Exception as e:
        print(f"Error saving performance learnings: {e}")

def run_performance_analysis(scraped_data):
    """
    Takes the raw scraped statistics, merges them with historical learnings,
    and runs a high-fidelity Gemini synthesis stage to generate actionable e-commerce insights.
    """
    if not scraped_data or not scraped_data.get("videos"):
        print("No recent YouTube performance data available for analysis. Retaining historical learnings.")
        return load_existing_learnings()

    print(f"Starting Gemini performance analysis on {len(scraped_data['videos'])} video(s)...")
    
    # Load past learnings to prevent memory loss across runs
    past_learnings = load_existing_learnings()
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Formulate a detailed instruction prompt
    prompt = f"""
You are the AI Business Strategy Engine for an automated e-commerce Affiliate Channel on YouTube Shorts.
Your goal is to analyze the performance of recent product promo videos, identify which physical products/categories/prices are viral, and generate structured recommendations to optimize our next product selections.

---
### PAST LEARNINGS (Historical Baseline)
{json.dumps(past_learnings, indent=2) if past_learnings else "None. This is the first analysis cycle."}

---
### RECENT PERFORMANCE DATA (Past 15 Days Uploads)
Total Channel Subscribers: {scraped_data.get('subscriber_count', 0)}
Videos Scraped:
{json.dumps(scraped_data['videos'], indent=2)}

---
### YOUR INSTRUCTIONS:
1. Compare views, likes, and comment metrics across the recent uploads.
2. Deduce what **product categories** (e.g. Smart Home, Tech Accessories, Kitchen Appliances, Fashion) got the highest engagement and views.
3. Determine what **price ranges** are working best for viewers (impulse buys under ₹1,000, mid-range ₹1,000-₹5,000, or premium items above ₹5,000).
4. Identify which **words, phrases, or hook styles** in the video titles drove higher click-through/views.
5. Highlight what **underperformed** (e.g., items with extremely low views compared to others).
6. Combine these recent findings with **PAST LEARNINGS** to create an updated, high-fidelity set of learnings. Do not forget past insights if they are still valid!

Output ONLY a valid JSON object with the following exact keys:
- "top_performing_categories": [list of 3-5 categories that drive high views/likes]
- "underperforming_categories": [list of categories that underperformed and should be avoided]
- "ideal_price_range": "impulse_buy_under_1000", "mid_range_1000_to_5000", or "premium_above_5000"
- "successful_hooks": [list of 3-5 terms, phrases, or hook templates that worked well in titles]
- "strategic_recommendations": [list of 3 actionable tips for the trend analyzer to discover better products next time]
"""

    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3)
        )
        
        raw = response.text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        
        new_learnings = json.loads(raw)
        
        # Save to file
        save_learnings(new_learnings)
        print("Gemini Analysis Successful:")
        print(json.dumps(new_learnings, indent=2))
        return new_learnings
        
    except Exception as e:
        print(f"Error during Gemini performance analysis: {e}")
        # Return past learnings as a fallback to prevent data loss
        return past_learnings

if __name__ == "__main__":
    # Test data
    sample_stats = {
        "subscriber_count": 1420,
        "videos": [
            {"title": "Unboxing the viral Air Fryer under 4000! 🍳 #Shorts", "views": 2500, "likes": 180, "date": "2026-05-18"},
            {"title": "Why everyone needs this Smart Watch in 2026! ⌚ #Shorts", "views": 1800, "likes": 110, "date": "2026-05-15"},
            {"title": "Noise Earbuds Review - Don't Buy! 🎧 #Shorts", "views": 3200, "likes": 250, "date": "2026-05-12"},
            {"title": "Premium Mechanical Keyboard for Gaming! ⌨️ #Shorts", "views": 250, "likes": 15, "date": "2026-05-08"}
        ]
    }
    run_performance_analysis(sample_stats)
