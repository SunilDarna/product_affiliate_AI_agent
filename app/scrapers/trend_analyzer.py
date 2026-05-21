from google import genai
from google.genai import types
import json
import re
from duckduckgo_search import DDGS
from app.config import GEMINI_API_KEY

# Default trending products if both DuckDuckGo and Gemini fail
DEFAULT_TRENDS = ["Wireless Earbuds", "Smartwatch", "Power Bank", "Air Fryer", "Bluetooth Speaker"]

def get_trending_topics_india():
    """
    Discovers 3-5 trending, high-demand product categories in India using
    DuckDuckGo search + Gemini LLM synthesis.
    Integrates historical video performance learnings to suggest higher-converting products.
    """
    import os
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Step 1: Load historical performance learnings if available
    learnings_context = ""
    # Define learnings file path relative to config WORKSPACE_DIR or relative to app root
    from app.config import WORKSPACE_DIR
    learnings_path = os.path.join(WORKSPACE_DIR, "learnings.json")
    
    if os.path.exists(learnings_path):
        try:
            with open(learnings_path, 'r') as f:
                learnings = json.load(f)
                if learnings:
                    print("Found historical performance learnings. Guiding trend selection...")
                    learnings_context = f"""
---
HISTORICAL CHANNEL PERFORMANCE & AUDIENCE FEEDBACK:
- Target Price Range: {learnings.get('ideal_price_range', 'Any')}
- High-Performing Product Categories: {', '.join(learnings.get('top_performing_categories', []))}
- UNDERPERFORMING Product Categories (AVOID): {', '.join(learnings.get('underperforming_categories', []))}
- Strategic Product Rules: {', '.join(learnings.get('strategic_recommendations', []))}
---
Instructions: Heavily weight your product category suggestions to match the high-performing categories and target price ranges, while completely avoiding any categories listed under underperforming.
"""
        except Exception as e:
            print(f"Warning: Could not read learnings in trend analyzer: {e}")

    # Fallback to general viral/high-return guidance if no performance history exists yet
    if not learnings_context:
        print("No historical channel performance learnings found. Defaulting to general viral e-commerce guidance.")
        learnings_context = """
---
NO HISTORICAL CHANNEL PERFORMANCE YET:
Instructions: Focus purely on identifying highly viral, high-demand, and high-commission physical products suitable for general Indian audiences. Target tech gadgets, smart lifestyle accessories, and innovative home appliances that are trending online and trigger high impulse buy conversions.
---
"""

    # Step 2: Gather raw signals from DuckDuckGo
    search_results = []
    try:
        with DDGS() as ddgs:
            results = ddgs.text("trending products India buy online 2024 best sellers", max_results=10)
            for r in results:
                search_results.append(r.get('title', '') + " " + r.get('body', ''))
        print(f"DuckDuckGo: Found {len(search_results)} trend signals.")
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}. Using Gemini-only trend analysis.")

    # Step 3: Synthesize with Gemini
    context = "\n".join(search_results[:8]) if search_results else "No search results available."
    prompt = f"""
You are a product trend analyst for the Indian e-commerce market.
Based on the web search results AND our channel's historical performance, identify the 5 most trending, 
high-demand physical product categories in India right now that are most likely to drive massive conversions.
{learnings_context}
Search Results:
{context}

Output ONLY a valid JSON array of 5 product category strings.
Example: ["Wireless Earbuds", "Smart Watch", "Air Fryer", "Power Bank", "LED Strip Lights"]
"""

    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4)
        )
        raw = re.sub(r"```json|```", "", response.text.strip()).strip()
        trends = json.loads(raw)
        if isinstance(trends, list) and len(trends) > 0:
            print(f"Gemini Trends: {trends}")
            return trends
    except Exception as e:
        print(f"Error fetching trends from Gemini: {e}")

    return DEFAULT_TRENDS


if __name__ == "__main__":
    trends = get_trending_topics_india()
    print("Trending:", trends)
