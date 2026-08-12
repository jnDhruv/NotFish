"""
Minimal backend for the phishing-detection MVP.

Endpoints:
  GET  /check?domain=example.com
       -> Tier 2 style lookup: runs the pre-filter (Tier "cheap check") and,
          if the pre-filter flagged the domain as suspicious enough, runs
          Tier 3 deep analysis: a *live* scrape of the candidate site
          (scraper.py) feeding both the visual similarity check
          (similarity.py) and the content/DOM similarity check
          (content_similarity.py). Returns a fused verdict. This is what
          the browser extension calls.

  GET  /health
       -> basic liveness check

Run with:
    uvicorn main:app --reload --port 8000

NOTE ON SCOPE:
- Tier 3 now does real "Rendering & Scraping" (README step 4/5) via
  Playwright: it screenshots the candidate site AND extracts its visible
  text, form fields, and favicon, then compares both the screenshot and
  the scraped content against a reference bank of known-legitimate sites
  (REFERENCE_SITES in scraper.py).
- If live scraping isn't available in a given environment (Playwright not
  installed, no browser binary, or the candidate site is unreachable), the
  API falls back to the original pre-saved-image demo path
  (DOMAIN_TO_SCREENSHOT below) rather than failing the request, so the
  MVP still runs offline/in restricted environments.
"""

import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from prefilter import prefilter_score
from similarity import visual_similarity_score
from scraper import scrape_site, load_reference_content_bank, build_reference_content_bank
from content_similarity import content_similarity_score

app = FastAPI(title="Phishing Domain Detection API (MVP)")

# Reference content bank (scraped legitimate sites) is loaded once at
# startup from disk cache. If it's empty (first run, cache never built),
# build_reference_content_bank() will scrape REFERENCE_SITES live and
# populate it - see scraper.py.
REFERENCE_CONTENT_BANK = load_reference_content_bank() or build_reference_content_bank()

# Allow the browser extension (running from a chrome-extension:// origin) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEST_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "test_images")

# Maps a domain -> a pre-saved screenshot filename, standing in for "we just
# rendered this candidate site with a headless browser." In the real system
# this step is done live by Playwright when a domain reaches Tier 3.
DOMAIN_TO_SCREENSHOT = {
    "paypa1-secure-login.com": "paypa1_phish.png",
    "secure-sbi-verify-login.com": "sbi_phish_clone.png",
    "randomnewsblog.com": "unrelated_site.png",
}


def fuse_scores(prefilter_result: dict, visual_result: dict | None, content_result: dict | None) -> dict:
    """
    Combines pre-filter risk, visual similarity, and content/DOM similarity
    into one final verdict.

    Weighting for the MVP:
      - Pre-filter always contributes, weight 40
      - Visual similarity contributes weight 30 (only if a screenshot was available)
      - Content similarity contributes weight 30 (only if a live scrape succeeded)
    Weights of components that didn't run are redistributed proportionally
    onto whichever components did run, so a domain that only got a
    pre-filter check isn't unfairly capped at 40/100.
    """
    components = [(prefilter_result["risk_score"], 0.40)]

    if visual_result and "similarity_score" in visual_result and not visual_result.get("error"):
        components.append((visual_result["similarity_score"], 0.30))

    if content_result and "content_similarity_score" in content_result and not content_result.get("error"):
        components.append((content_result["content_similarity_score"], 0.30))

    total_weight = sum(w for _, w in components)
    final_score = round(sum(score * w for score, w in components) / total_weight)

    if final_score >= 70:
        verdict = "phishing_suspected"
    elif final_score >= 35:
        verdict = "suspicious"
    else:
        verdict = "likely_safe"

    return {"final_score": final_score, "verdict": verdict}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/check")
def check_domain(domain: str = Query(..., description="Domain to check, e.g. paypa1-secure-login.com")):
    domain = domain.lower().strip()

    # --- Tier 1/2: pre-filter check (cheap, always runs) ---
    prefilter_result = prefilter_score(domain)

    # --- Tier 3: only render/scrape + run deep analysis if the pre-filter
    #     flagged this domain as suspicious enough to justify the (in
    #     production, expensive) live browser render. ---
    visual_result = None
    content_result = None
    scrape_error = None

    if prefilter_result["risk_score"] >= 30:
        scraped = scrape_site(f"https://{domain}", save_screenshot_as=f"{domain.replace('/', '_')}.png")

        if not scraped.get("error"):
            visual_result = visual_similarity_score(scraped["screenshot_path"])
            content_result = content_similarity_score(scraped, REFERENCE_CONTENT_BANK)
        else:
            scrape_error = scraped["error"]
            # Fall back to the original pre-saved-image demo path so the API
            # still returns a useful visual signal when live scraping isn't
            # available (Playwright not installed, offline env, etc.).
            if domain in DOMAIN_TO_SCREENSHOT:
                screenshot_path = os.path.join(TEST_IMAGES_DIR, DOMAIN_TO_SCREENSHOT[domain])
                visual_result = visual_similarity_score(screenshot_path)

    fused = fuse_scores(prefilter_result, visual_result, content_result)

    return {
        "domain": domain,
        "prefilter": prefilter_result,
        "visual_analysis": visual_result,
        "content_analysis": content_result,
        "scrape_error": scrape_error,
        **fused,
    }


@app.post("/admin/refresh-reference-bank")
def refresh_reference_bank():
    """
    Re-scrapes every URL in scraper.REFERENCE_SITES and rebuilds the cached
    reference content bank used by /check for content similarity. Intended
    to be called periodically (e.g. a daily cron/scheduled job) so the
    "genuine" side of the comparison doesn't go stale as reference sites
    redesign their pages - mirrors the "Reference Brand Bank" refresh
    described in the architecture doc.
    """
    global REFERENCE_CONTENT_BANK
    REFERENCE_CONTENT_BANK = build_reference_content_bank(force_refresh=True)
    return {
        "status": "refreshed",
        "brands": list(REFERENCE_CONTENT_BANK.keys()),
    }
