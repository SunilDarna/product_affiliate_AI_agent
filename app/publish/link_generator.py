import asyncio
import json
import os
import re
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from playwright.async_api import async_playwright

from app.config import SECRETS, WORKSPACE_DIR
from app.utils.browser_helper import ensure_chrome_debugging_active


KIMI_BASE_URL = "http://127.0.0.1:10086"
KIMI_COMMAND_URL = f"{KIMI_BASE_URL}/command"
KIMI_BIN = os.path.expanduser("~/.kimi-webbridge/bin/kimi-webbridge")
AMAZON_SESSION = "amazon-affiliate"
AMAZON_SHORT_LINK_RE = re.compile(r"^https?://(?:amzn\.in|amzn\.to)/[A-Za-z0-9_/-]+/?$")


@dataclass
class AffiliateLinkResult:
    url: str
    method: str
    is_shortlink: bool
    diagnostics: List[str]


def extract_asin(url):
    """
    Extracts the Amazon Standard Identification Number (ASIN) from any Amazon URL.
    Handles standard product pages, search results, and encoded redirect/sspa URLs.
    """
    decoded_url = urllib.parse.unquote(url)

    asin_match = re.search(r'/(?:dp|gp/product|d)/(B[0-9A-Z]{9}|\d{9}[0-9X])', decoded_url, re.IGNORECASE)
    if asin_match:
        return asin_match.group(1)

    query_params = urllib.parse.parse_qs(urllib.parse.urlparse(decoded_url).query)
    for key, values in query_params.items():
        if key.lower() in ['asin', 'dp'] and values:
            return values[0]

    return None


def build_tag_fallback_url(product_url, tag):
    """
    Cleans up any messy/redirect Amazon URL and builds a direct Associate-tag URL.
    This is clickable and monetized, but it is not the SiteStripe short link.
    """
    if not tag:
        return product_url

    asin = extract_asin(product_url)
    if asin:
        return f"https://www.amazon.in/dp/{asin}?tag={tag}"

    parsed_url = urllib.parse.urlparse(product_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params['tag'] = [tag]

    for bad_key in ['ref', 'ref_', 'qid', 'sr', 'pf_rd']:
        query_params.pop(bad_key, None)

    new_query = urllib.parse.urlencode(query_params, doseq=True)
    new_url = urllib.parse.ParseResult(
        scheme=parsed_url.scheme,
        netloc=parsed_url.netloc,
        path=parsed_url.path,
        params=parsed_url.params,
        query=new_query,
        fragment=parsed_url.fragment
    )
    return urllib.parse.urlunparse(new_url)


def _normalize_product_url(product_url: str) -> str:
    asin = extract_asin(product_url)
    return f"https://www.amazon.in/dp/{asin}" if asin else product_url


def _is_shortlink(url: str) -> bool:
    return bool(url and AMAZON_SHORT_LINK_RE.match(url.strip()))


def validate_amazon_shortlink(url: str) -> bool:
    """Public guard used by the pipeline before upload."""
    return _is_shortlink(url)


def _save_diagnostic(name: str, data: Any) -> None:
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        path = os.path.join(WORKSPACE_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f, indent=2)
        print(f"Saved affiliate-link diagnostic: {path}")
    except Exception as exc:
        print(f"Could not save affiliate-link diagnostic {name}: {exc}")


def _run_kimi_cli(*args: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(KIMI_BIN):
        return None

    try:
        proc = subprocess.run(
            [KIMI_BIN, *args],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except Exception as exc:
        return {"error": str(exc)}

    raw = (proc.stdout or proc.stderr or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"raw": raw}

    parsed["returncode"] = proc.returncode
    return parsed


def _http_status(timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(f"{KIMI_BASE_URL}/status", timeout=timeout)
        if response.status_code != 200:
            return {"running": False, "error": f"HTTP {response.status_code}: {response.text[:300]}"}
        return response.json()
    except Exception as exc:
        return {"running": False, "error": str(exc)}


def _ensure_kimi_ready(diagnostics: List[str]) -> bool:
    """
    Starts/restarts Kimi when possible and confirms both daemon and extension are ready.
    If the current process is sandbox-blocked from localhost, this returns False with
    a clear diagnostic instead of falling through silently.
    """
    status = _http_status()
    if status and status.get("running") and status.get("extension_connected"):
        return True

    diagnostics.append(f"Kimi HTTP status not ready: {status}")

    cli_status = _run_kimi_cli("status")
    diagnostics.append(f"Kimi CLI status: {cli_status}")

    if cli_status and not cli_status.get("running") and os.path.exists(KIMI_BIN):
        diagnostics.append("Starting Kimi WebBridge daemon via CLI.")
        diagnostics.append(f"Kimi CLI start: {_run_kimi_cli('start')}")
        time.sleep(2)
        status = _http_status()
        if status and status.get("running") and status.get("extension_connected"):
            return True

    if cli_status and cli_status.get("running") and not cli_status.get("extension_connected"):
        print("Kimi WebBridge is running, but the browser extension is not connected.")
        print("Open Chrome/Edge with the Kimi WebBridge extension enabled, then rerun the pipeline.")
        return False

    if status and "Operation not permitted" in str(status.get("error", "")):
        print("Kimi WebBridge is blocked by the current sandbox from connecting to 127.0.0.1:10086.")
        print("Run the pipeline from a normal terminal, or approve localhost/network access for this command.")

    return False


def _command_ok(payload: Dict[str, Any]) -> bool:
    return bool(payload.get("ok") or payload.get("success"))


def _command_value(payload: Dict[str, Any]) -> Any:
    if "data" in payload and isinstance(payload["data"], dict) and "value" in payload["data"]:
        return payload["data"]["value"]
    if "value" in payload:
        return payload["value"]
    if "result" in payload and isinstance(payload["result"], dict) and "value" in payload["result"]:
        return payload["result"]["value"]
    if "result" in payload:
        return payload["result"]
    return payload


async def _post_kimi_command(payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: requests.post(KIMI_COMMAND_URL, json=payload, timeout=timeout)
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    body["_http_status"] = response.status_code
    return body


SITE_STRIPE_EXTRACTION_JS = """
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const visible = el => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const fireClick = el => {
    if (!el) return;
    el.scrollIntoView({block: 'center', inline: 'center'});
    for (const type of ['mouseover', 'mousedown', 'mouseup', 'click']) {
      el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    }
  };
  const readShortlink = () => {
    const field = document.querySelector('#amzn-ss-text-shortlink-textarea, textarea[id*="shortlink"], input[id*="shortlink"]');
    const value = field && (field.value || field.textContent || '').trim();
    if (value && /^https?:\\/\\/(amzn\\.in|amzn\\.to)\\//.test(value)) return value;
    const bodyText = document.body ? document.body.innerText : '';
    const match = bodyText.match(/https?:\\/\\/(?:amzn\\.in|amzn\\.to)\\/[A-Za-z0-9_/-]+/);
    return match ? match[0] : '';
  };
  const selectors = [
    '#amzn-ss-get-link-button',
    '#amzn-ss-text-link button',
    '#amzn-ss-text-link',
    '#amzn-ss-get-link-container button',
    '#amzn-ss-get-link-container [data-action="amzn-ss-show-text-popover"]'
  ];

  let stripeLink = null;
  for (let i = 0; i < 40; i++) {
    for (const selector of selectors) {
      const candidate = [...document.querySelectorAll(selector)].find(el => visible(el) || el.id === 'amzn-ss-text-link');
      if (candidate) {
        stripeLink = candidate;
        break;
      }
    }
    if (stripeLink) break;
    await sleep(500);
  }

  if (!stripeLink) {
    return {
      success: false,
      error: 'Amazon SiteStripe text link element not found',
      title: document.title,
      url: location.href,
      hasSiteStripe: !!document.querySelector('[id*="amzn-ss"], [class*="amzn-ss"]'),
      stripeHtml: (document.querySelector('#nav-AssociateStripe') || {}).innerText || ''
    };
  }

  fireClick(stripeLink);

  const textareaSelectors = [
    'textarea#amzn-ss-text-shortlink-textarea',
    '#amzn-ss-text-shortlink-textarea',
    'textarea[id*="shortlink"]',
    'input[id*="shortlink"]',
    'textarea'
  ];

  let field = null;
  for (let i = 0; i < 40; i++) {
    const generateButton = document.querySelector('#amzn-ss-get-link-btn-text-announce');
    if (generateButton && !generateButton.disabled) fireClick(generateButton);

    const generated = readShortlink();
    if (generated) return { success: true, link: generated, title: document.title, url: location.href };

    for (const selector of textareaSelectors) {
      const candidate = [...document.querySelectorAll(selector)]
        .find(el => visible(el) && (el.value || '').trim().startsWith('http'));
      if (candidate) {
        field = candidate;
        break;
      }
    }
    if (field) break;
    await sleep(500);
  }

  if (!field) {
    return {
      success: false,
      error: 'SiteStripe shortlink field did not appear or was empty',
      title: document.title,
      url: location.href,
      hasSiteStripe: !!document.querySelector('[id*="amzn-ss"], [class*="amzn-ss"]')
    };
  }

  return { success: true, link: field.value.trim(), title: document.title, url: location.href };
})()
"""


async def get_affiliate_link_via_kimi_webbridge(product_url: str) -> Optional[AffiliateLinkResult]:
    """
    Retrieves an Amazon SiteStripe short link using Kimi WebBridge.
    Assumes the browser extension is connected to a profile logged into Amazon Associates.
    """
    diagnostics: List[str] = []
    if not _ensure_kimi_ready(diagnostics):
        _save_diagnostic("affiliate_link_kimi_diagnostic.json", diagnostics)
        return None

    target_url = _normalize_product_url(product_url)
    print(f"Affiliate link: navigating via Kimi WebBridge to {target_url}")

    nav_payload = {
        "action": "navigate",
        "args": {"url": target_url, "newTab": True, "group_title": "Amazon Affiliate"},
        "session": AMAZON_SESSION,
    }

    try:
        nav_result = await _post_kimi_command(nav_payload, timeout=30)
        diagnostics.append(f"Kimi navigate result: {nav_result}")
        if nav_result.get("_http_status") != 200 or not _command_ok(nav_result):
            _save_diagnostic("affiliate_link_kimi_diagnostic.json", diagnostics)
            print(f"Kimi WebBridge navigation failed: {nav_result}")
            return None
    except Exception as exc:
        diagnostics.append(f"Kimi navigation exception: {exc}")
        _save_diagnostic("affiliate_link_kimi_diagnostic.json", diagnostics)
        print(f"Kimi WebBridge navigation request failed: {exc}")
        return None

    await asyncio.sleep(5)

    eval_payload = {
        "action": "evaluate",
        "args": {"code": SITE_STRIPE_EXTRACTION_JS},
        "session": AMAZON_SESSION,
    }

    try:
        eval_result = await _post_kimi_command(eval_payload, timeout=40)
        diagnostics.append(f"Kimi evaluate result: {eval_result}")
        if eval_result.get("_http_status") == 200 and _command_ok(eval_result):
            eval_value = _command_value(eval_result)
            if isinstance(eval_value, dict) and eval_value.get("success"):
                link = eval_value.get("link", "").strip()
                if _is_shortlink(link):
                    print(f"Affiliate link: extracted SiteStripe shortlink via Kimi: {link}")
                    await _close_kimi_tab()
                    return AffiliateLinkResult(link, "kimi-sitestripe", True, diagnostics)
                diagnostics.append(f"Kimi returned non-shortlink value: {link}")
            else:
                diagnostics.append(f"Kimi SiteStripe extraction failed: {eval_value}")
                print(f"Kimi SiteStripe extraction failed: {eval_value}")
        else:
            print(f"Kimi WebBridge evaluate failed: {eval_result}")
    except Exception as exc:
        diagnostics.append(f"Kimi evaluate exception: {exc}")
        print(f"Kimi WebBridge evaluate request failed: {exc}")

    _save_diagnostic("affiliate_link_kimi_diagnostic.json", diagnostics)
    return None


async def _close_kimi_tab() -> None:
    try:
        await _post_kimi_command({"action": "close_tab", "session": AMAZON_SESSION}, timeout=5)
    except Exception:
        pass


async def get_affiliate_link_via_cdp(product_url: str) -> Optional[AffiliateLinkResult]:
    diagnostics: List[str] = []
    if not ensure_chrome_debugging_active():
        diagnostics.append("Chrome remote debugging was not active and could not be enabled.")
        _save_diagnostic("affiliate_link_cdp_diagnostic.json", diagnostics)
        return None

    target_url = _normalize_product_url(product_url)

    async with async_playwright() as p:
        page = None
        try:
            print(f"Affiliate link: connecting to Chrome CDP for {target_url}")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = await context.new_page()
            await page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            result = await page.evaluate(SITE_STRIPE_EXTRACTION_JS)
            diagnostics.append(f"CDP SiteStripe result: {result}")
            if isinstance(result, dict) and result.get("success"):
                link = result.get("link", "").strip()
                if _is_shortlink(link):
                    print(f"Affiliate link: extracted SiteStripe shortlink via CDP: {link}")
                    return AffiliateLinkResult(link, "cdp-sitestripe", True, diagnostics)
                diagnostics.append(f"CDP returned non-shortlink value: {link}")

            html = await page.content()
            _save_diagnostic("affiliate_link_cdp_page.html", html[:500000])
            print(f"Chrome CDP SiteStripe extraction failed: {result}")
        except Exception as exc:
            diagnostics.append(f"CDP exception: {exc}")
            print(f"Chrome CDP affiliate automation failed: {exc}")
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    _save_diagnostic("affiliate_link_cdp_diagnostic.json", diagnostics)
    return None


async def _get_amazon_affiliate_link_result(product_url: str, require_shortlink: bool = True) -> AffiliateLinkResult:
    """
    Retrieves the Amazon affiliate link.
    Primary: Kimi WebBridge SiteStripe.
    Fallback: Chrome CDP SiteStripe.
    Last resort: full Associate-tag URL, only when require_shortlink=False.
    """
    associate_tag = SECRETS.get("amazon_associate_tag", "")

    print("Affiliate link: trying Kimi WebBridge SiteStripe shortlink...")
    kimi_result = await get_affiliate_link_via_kimi_webbridge(product_url)
    if kimi_result and kimi_result.is_shortlink:
        return kimi_result

    print("Affiliate link: trying Chrome CDP SiteStripe shortlink fallback...")
    cdp_result = await get_affiliate_link_via_cdp(product_url)
    if cdp_result and cdp_result.is_shortlink:
        return cdp_result

    if require_shortlink:
        raise RuntimeError(
            "Could not generate an actual Amazon SiteStripe short link. "
            "Make sure Kimi WebBridge is reachable, the browser extension is connected, "
            "Chrome is logged into Amazon Associates, and SiteStripe is enabled. "
            "No video should be uploaded with a placeholder/default link."
        )

    if associate_tag:
        fallback_link = build_tag_fallback_url(product_url, associate_tag)
        print(f"Affiliate link: using full tagged URL fallback: {fallback_link}")
        return AffiliateLinkResult(fallback_link, "tagged-url-fallback", False, [])

    print("Warning: no amazon_associate_tag found in secrets.json. Returning original URL.")
    return AffiliateLinkResult(product_url, "original-url-fallback", False, [])


def generate_affiliate_link(product_url: str, require_shortlink: bool = True) -> str:
    """Synchronous wrapper for generating an Amazon SiteStripe short link."""
    link = asyncio.run(_get_amazon_affiliate_link_result(product_url, require_shortlink=require_shortlink)).url
    if require_shortlink and not validate_amazon_shortlink(link):
        raise RuntimeError(f"Generated affiliate link is not an Amazon short link: {link}")
    return link


if __name__ == "__main__":
    pass
