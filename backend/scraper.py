"""
scraper.py

Live web-scraping module - this is the real implementation of the
"Rendering & Scraping" step from the architecture doc (step 4 in the
README workflow), which main.py previously stood in for using pre-saved
images in test_images/.

Renders a candidate URL with a headless browser (Playwright) and extracts
everything the fusion engine needs to compare it against a genuine site:
  - a full-page screenshot                  -> feeds similarity.py (visual)
  - visible page text                       -> feeds content_similarity.py
  - DOM structure: forms, input field names/types, title, favicon
  - a favicon perceptual hash (cheap, high-signal - many clones lazily
    reuse the real site's favicon, or fall back to a generic default)

This module also builds and caches the "genuine" side of the comparison:
given a small list of known-legitimate brand URLs (REFERENCE_SITES), it
scrapes each once and stores what it finds, so content_similarity.py has
real reference data to diff a candidate against - not just images.

Requires Playwright's Chromium browser to be installed once:
    pip install playwright
    playwright install chromium
If Playwright or its browser binary isn't available, scrape_site() returns
a result dict with "error" set rather than raising, so callers (main.py)
can fall back gracefully instead of crashing the API.
"""

import io
import json
import os
import time
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

import imagehash
from PIL import Image

BACKEND_DIR = os.path.dirname(__file__)
SCREENSHOTS_DIR = os.path.join(BACKEND_DIR, "scraped_screenshots")
REFERENCE_CONTENT_DIR = os.path.join(BACKEND_DIR, "reference_content")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(REFERENCE_CONTENT_DIR, exist_ok=True)

# Known-legitimate URLs used to build the reference content bank. Keyed by
# the same brand names used in reference_images/ (e.g. "paypal_genuine" ->
# brand "paypal") so the visual signal and the content signal both
# attribute to the same brand. Extend this list to grow the reference bank -
# this is the "Reference Brand Bank" from the architecture doc.
REFERENCE_SITES = {
    "paypal": "https://www.paypal.com/signin",
    "sbi": "https://www.onlinesbi.sbi/",
    "amazon": "https://www.amazon.com/ap/signin",
}

DEFAULT_TIMEOUT_MS = 15000


def _extract_forms(page) -> list:
    """Pulls every form's action/method and each field's name, type, placeholder."""
    return page.eval_on_selector_all(
        "form",
        """
        forms => forms.map(f => ({
            action: f.action || null,
            method: (f.method || 'get').toLowerCase(),
            fields: Array.from(f.querySelectorAll('input, textarea, select')).map(el => ({
                name: el.name || el.id || null,
                type: el.type || el.tagName.toLowerCase(),
                placeholder: el.placeholder || null,
            })),
        }))
        """,
    )


def _extract_favicon_url(page, base_url: str) -> str:
    href = page.eval_on_selector("link[rel~='icon']", "el => el && el.getAttribute('href')")
    if href:
        return urljoin(base_url, href)
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def scrape_site(url: str, save_screenshot_as: str | None = None) -> dict:
    """
    Renders `url` in a headless browser and extracts everything needed for
    content + visual comparison against a reference site.

    Returns a dict:
        {
          "url", "final_url", "title", "visible_text" (truncated to 20k chars),
          "forms": [...], "favicon_hash": str or None,
          "screenshot_path": str or None, "error": str or None,
        }
    `error` is set (and other fields left mostly empty) instead of raising,
    so a single unreachable/slow candidate site can't take down a batch job
    or the live API request.
    """
    result = {
        "url": url,
        "final_url": None,
        "title": None,
        "visible_text": "",
        "forms": [],
        "favicon_hash": None,
        "screenshot_path": None,
        "error": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        result["error"] = "playwright not installed (pip install playwright && playwright install chromium)"
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                page.goto(url, timeout=DEFAULT_TIMEOUT_MS, wait_until="networkidle")
            except Exception:
                # Some sites never go fully idle (polling widgets, ads). Fall
                # back to "loaded" before giving up entirely.
                page.goto(url, timeout=DEFAULT_TIMEOUT_MS, wait_until="load")

            result["final_url"] = page.url
            result["title"] = page.title()
            try:
                result["visible_text"] = page.inner_text("body")[:20000]
            except Exception:
                result["visible_text"] = ""
            try:
                result["forms"] = _extract_forms(page)
            except Exception:
                result["forms"] = []

            screenshot_bytes = page.screenshot(full_page=False)
            if save_screenshot_as:
                screenshot_path = os.path.join(SCREENSHOTS_DIR, save_screenshot_as)
                with open(screenshot_path, "wb") as f:
                    f.write(screenshot_bytes)
                result["screenshot_path"] = screenshot_path

            try:
                favicon_url = _extract_favicon_url(page, result["final_url"] or url)
                resp = page.request.get(favicon_url, timeout=5000)
                if resp.ok:
                    favicon_img = Image.open(io.BytesIO(resp.body()))
                    result["favicon_hash"] = str(imagehash.phash(favicon_img))
            except Exception:
                pass  # missing/broken favicon isn't fatal - just no favicon signal

            browser.close()
    except Exception as e:
        result["error"] = str(e)

    return result


def build_reference_content_bank(force_refresh: bool = False) -> dict:
    """
    Scrapes every URL in REFERENCE_SITES once and caches the extracted
    content to reference_content/<brand>.json. Re-run this (e.g. from a
    periodic job) to keep the "genuine" side of the comparison current -
    this mirrors the "Reference Brand Bank refresh" described in the
    architecture doc. Cached entries are reused unless force_refresh=True,
    so this is cheap to call on every API startup.
    """
    bank = {}
    for brand, url in REFERENCE_SITES.items():
        cache_path = os.path.join(REFERENCE_CONTENT_DIR, f"{brand}.json")
        if os.path.exists(cache_path) and not force_refresh:
            with open(cache_path) as f:
                bank[brand] = json.load(f)
            continue

        scraped = scrape_site(url, save_screenshot_as=f"{brand}_reference.png")
        scraped["scraped_at"] = time.time()
        with open(cache_path, "w") as f:
            json.dump(scraped, f, indent=2)
        bank[brand] = scraped
    return bank


def load_reference_content_bank() -> dict:
    """Loads cached reference content from disk without re-scraping (fast path for API startup)."""
    bank = {}
    if not os.path.isdir(REFERENCE_CONTENT_DIR):
        return bank
    for fname in os.listdir(REFERENCE_CONTENT_DIR):
        if fname.endswith(".json"):
            brand = fname[:-5]
            with open(os.path.join(REFERENCE_CONTENT_DIR, fname)) as f:
                bank[brand] = json.load(f)
    return bank


if __name__ == "__main__":
    if not PLAYWRIGHT_AVAILABLE:
        print("Playwright isn't installed. Run:\n  pip install playwright\n  playwright install chromium")
    else:
        print("Building reference content bank from REFERENCE_SITES...")
        bank = build_reference_content_bank(force_refresh=True)
        for brand, data in bank.items():
            print(
                f"  {brand}: title={data.get('title')!r}, forms={len(data.get('forms', []))}, "
                f"favicon_hash={data.get('favicon_hash')}, error={data.get('error')}"
            )
