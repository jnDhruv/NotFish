"""
content_similarity.py

Tier 3 (a) content/code similarity - compares a live-scraped candidate page
(see scraper.py) against the cached reference content bank built from known
legitimate sites. This is the DOM/text counterpart to similarity.py's (b)
visual/image comparison; main.py fuses both into the final score.

Signals combined (each normalized to 0-100):
  - visible text similarity   - rapidfuzz token_sort_ratio on page text
  - form field similarity     - Jaccard over the set of (name, type) input
                                 fields; a cloned login page almost always
                                 keeps the real site's field names so it
                                 still posts credentials somewhere useful
  - favicon match              - many clones lazily reuse the real favicon
  - page title similarity

Weighted sum gives one 0-100 content_similarity_score plus a breakdown, so
the extension UI can show *why* a page was flagged (e.g. "Form fields 92%
match PayPal's login page" is a more convincing signal to show a user than
a single opaque number).
"""

from rapidfuzz import fuzz

WEIGHTS = {"text": 0.35, "forms": 0.30, "favicon": 0.20, "title": 0.15}


def _form_field_set(forms: list) -> set:
    fields = set()
    for form in forms or []:
        for field in form.get("fields", []):
            name = (field.get("name") or "").lower()
            ftype = (field.get("type") or "").lower()
            if name:
                fields.add(f"{name}:{ftype}")
    return fields


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def content_similarity_score(candidate: dict, reference_bank: dict) -> dict:
    """
    Compares `candidate` (output of scraper.scrape_site) against every entry
    in `reference_bank` (output of scraper.load_reference_content_bank /
    build_reference_content_bank). Returns the closest-matching brand and a
    0-100 similarity score with a per-signal breakdown.

    Returns:
        {
          "content_similarity_score": int 0-100,
          "closest_match": str or None,
          "breakdown": {"text_similarity", "form_field_similarity",
                        "favicon_match", "title_similarity"},
          "error": str or None,
        }
    """
    if candidate.get("error"):
        return {
            "content_similarity_score": 0,
            "closest_match": None,
            "breakdown": {},
            "error": candidate["error"],
        }
    if not reference_bank:
        return {
            "content_similarity_score": 0,
            "closest_match": None,
            "breakdown": {},
            "error": "reference content bank is empty - run scraper.build_reference_content_bank() first",
        }

    candidate_fields = _form_field_set(candidate.get("forms"))
    candidate_text = candidate.get("visible_text") or ""
    candidate_title = candidate.get("title") or ""
    candidate_favicon = candidate.get("favicon_hash")

    best_brand = None
    best_score = -1.0
    best_breakdown = {}

    for brand, ref in reference_bank.items():
        if ref.get("error"):
            continue  # reference itself failed to scrape - skip, don't compare against garbage

        text_sim = fuzz.token_sort_ratio(candidate_text[:5000], (ref.get("visible_text") or "")[:5000])
        form_sim = _jaccard(candidate_fields, _form_field_set(ref.get("forms"))) * 100
        title_sim = fuzz.ratio(candidate_title, ref.get("title") or "")
        favicon_sim = 100.0 if candidate_favicon and candidate_favicon == ref.get("favicon_hash") else 0.0

        combined = (
            text_sim * WEIGHTS["text"]
            + form_sim * WEIGHTS["forms"]
            + favicon_sim * WEIGHTS["favicon"]
            + title_sim * WEIGHTS["title"]
        )

        if combined > best_score:
            best_score = combined
            best_brand = brand
            best_breakdown = {
                "text_similarity": round(text_sim),
                "form_field_similarity": round(form_sim),
                "favicon_match": favicon_sim == 100.0,
                "title_similarity": round(title_sim),
            }

    if best_brand is None:
        return {
            "content_similarity_score": 0,
            "closest_match": None,
            "breakdown": {},
            "error": "every reference bank entry had a scrape error",
        }

    return {
        "content_similarity_score": round(max(0, best_score)),
        "closest_match": best_brand,
        "breakdown": best_breakdown,
        "error": None,
    }
