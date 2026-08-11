"""
Minimal backend for the phishing-detection MVP.

Endpoints:
  GET  /check?domain=example.com
       -> Tier 2 style lookup: runs the pre-filter (Tier "cheap check") and,
          if a screenshot for this domain exists in test_images/, also runs
          the visual similarity check (Tier 3 stand-in). Returns a fused
          verdict. This is what the browser extension calls.

  GET  /health
       -> basic liveness check

Run with:
    uvicorn main:app --reload --port 8000

NOTE ON SCOPE (read this before extending):
- In the full system design, screenshots come from a live headless browser
  (Playwright) rendering the candidate site, and the reference bank / model
  is a CNN embedding, not perceptual hashing. Both are swappable behind the
  same function signatures used here (see similarity.py's module docstring).
- This MVP intentionally uses pre-saved test images so the demo works
  without live browser automation or network access — that's a documented
  simplification, not an oversight.
"""

import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from prefilter import prefilter_score
from similarity import visual_similarity_score

app = FastAPI(title="Phishing Domain Detection API (MVP)")

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


def fuse_scores(prefilter_result: dict, visual_result: dict | None) -> dict:
    """
    Combines pre-filter risk and visual similarity into one final verdict.
    Simple weighted approach for the MVP:
      - Pre-filter contributes up to 50 points
      - Visual similarity contributes up to 50 points (only if we had an image to check)
    """
    prefilter_component = prefilter_result["risk_score"] * 0.5

    if visual_result and "similarity_score" in visual_result:
        visual_component = visual_result["similarity_score"] * 0.5
        final_score = round(prefilter_component + visual_component)
    else:
        # No screenshot available (Tier 3 not triggered) -> rely on pre-filter alone
        final_score = round(prefilter_result["risk_score"])

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

    # --- Tier 1/2 stand-in: pre-filter check (cheap, always runs) ---
    prefilter_result = prefilter_score(domain)

    # --- Tier 3 stand-in: only run visual analysis if pre-filter flagged it
    #     as suspicious enough to be worth the (in production, expensive) check ---
    visual_result = None
    if prefilter_result["risk_score"] >= 30 and domain in DOMAIN_TO_SCREENSHOT:
        screenshot_path = os.path.join(TEST_IMAGES_DIR, DOMAIN_TO_SCREENSHOT[domain])
        visual_result = visual_similarity_score(screenshot_path)

    fused = fuse_scores(prefilter_result, visual_result)

    return {
        "domain": domain,
        "prefilter": prefilter_result,
        "visual_analysis": visual_result,
        **fused,
    }
