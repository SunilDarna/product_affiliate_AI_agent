import sys
import asyncio
from app.publish.link_generator import generate_affiliate_link

def main():
    # Use a real Amazon India product URL for testing
    product_url = "https://www.amazon.in/dp/B0CX92Z4P8"
    if len(sys.argv) > 1:
        product_url = sys.argv[1]
        
    print(f"--- TESTING AMAZON AFFILIATE LINK GENERATION ---")
    print(f"Product URL: {product_url}")
    print(f"Generating link...")
    
    link = generate_affiliate_link(product_url)
    
    print("\n--- RESULTS ---")
    print(f"Generated Link: {link}")
    print(f"Success: {link != product_url and 'tag=' not in link}")
    print(f"------------------------------------------------")

if __name__ == "__main__":
    main()
