import requests
import time
import sys

def main():
    product_url = "https://www.amazon.in/dp/B0CX92Z4P8"
    if len(sys.argv) > 1:
        product_url = sys.argv[1]

    daemon_url = "http://127.0.0.1:10086/command"
    session_name = "amazon-affiliate"

    print("1. Checking WebBridge status...")
    try:
        r = requests.get("http://127.0.0.1:10086/status", timeout=2)
        print(f"Status: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Failed status check: {e}")
        return

    print(f"2. Navigating to {product_url}...")
    nav_payload = {
        "action": "navigate",
        "args": {
            "url": product_url,
            "newTab": True
        },
        "session": session_name
    }
    try:
        r = requests.post(daemon_url, json=nav_payload, timeout=8)
        print(f"Nav response: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Nav request failed: {e}")
        return

    print("3. Sleeping 3 seconds...")
    time.sleep(3)

    print("4. Evaluating script on page...")
    js_code = """
    (() => {
        const link = document.querySelector('li#amzn-ss-text-link a');
        const title = document.title;
        return { has_stripe: !!link, title: title };
    })()
    """
    eval_payload = {
        "action": "evaluate",
        "args": {
            "code": js_code
        },
        "session": session_name
    }
    try:
        r = requests.post(daemon_url, json=eval_payload, timeout=5)
        print(f"Eval response: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Eval request failed: {e}")

    print("5. Closing tab...")
    try:
        r = requests.post(daemon_url, json={"action": "close_tab", "session": session_name}, timeout=3)
        print(f"Close tab response: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Close tab failed: {e}")

if __name__ == "__main__":
    main()
