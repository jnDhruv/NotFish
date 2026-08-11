"""
Tier 1 pre-filter: cheap, fast checks that run before any deep analysis.

Uses a large static list of well-known domains (protected_domains.json,
~10,000 domains pulled from a public top-sites ranking) instead of a small
hardcoded brand list, so typosquat/lookalike detection works against almost
any famous website, not just a handful of manually chosen brands.

- Exact-match whitelist: if the domain IS one of the known top domains,
  it's genuine -> risk 0, skip everything else.
- Typosquat / lexical distance: is this domain suspiciously similar to one
  of the known top domains without being an exact match?
- Suspicious pattern check: keyword stuffing, excessive hyphens, etc.

NOTE ON SCALE: this file ships ~10k domains for the MVP demo. The same
mechanism scales to 100k-1M (the source dataset goes that large) - the
only cost is a slightly larger file and marginally more compute per check,
both of which are still small (see benchmark note in similarity design docs).
"""

import json
import os
from rapidfuzz import fuzz

DOMAIN_LIST_PATH = os.path.join(os.path.dirname(__file__), "protected_domains.json")

# Compound second-level suffixes where the "brand" is the label BEFORE these
# two parts (e.g. sbi.co.in -> brand is "sbi", not "co").
COMPOUND_SUFFIXES = {
    "co.in", "co.uk", "co.jp", "com.cn", "com.br", "com.au", "ne.jp", "or.jp",
    "co.kr", "ac.in", "gov.in", "co.za", "com.mx", "co.nz", "com.tw", "co.id",
}

# How many top-ranked domains to actually use for fuzzy typosquat comparison.
# Restricting to the most-famous subset avoids false positives from obscure,
# generic-word-like long-tail domains further down the list (e.g. some
# rank-9000 site literally named "home.pl") while still covering essentially
# every brand a user would recognize. Exact-match whitelist still uses the
# FULL list, not just this subset.
TYPOSQUAT_CANDIDATE_LIMIT = 10000

# Generic words that show up as domain "brand" names but are too common to
# safely use for substring/fuzzy matching (would false-positive constantly).
GENERIC_WORD_BLOCKLIST = {
    "mail", "home", "news", "shop", "blog", "help", "live", "mobile", "online",
    "web", "world", "group", "team", "media", "click", "deals", "best", "top",
    "free", "get", "new", "app", "store", "service", "cloud", "data", "tech",
    "digital", "smart", "network", "systems", "solutions", "my", "go", "info",
}

SUSPICIOUS_KEYWORDS = ["secure", "verify", "login", "update", "confirm", "account", "signin"]

HOMOGLYPH_MAP = {
    "0": "o",
    "1": "l",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
}


def extract_brand(domain: str) -> str:
    """
    Extracts the 'owning brand' label from a domain, correctly handling
    subdomains (login.tmall.com -> tmall) and compound TLDs (sbi.co.in -> sbi).
    """
    parts = domain.split(".")
    if len(parts) < 2:
        return domain
    last_two = ".".join(parts[-2:])
    if last_two in COMPOUND_SUFFIXES and len(parts) >= 3:
        return parts[-3]
    return parts[-2]


def load_domain_list() -> list:
    if not os.path.exists(DOMAIN_LIST_PATH):
        return []
    with open(DOMAIN_LIST_PATH) as f:
        return json.load(f)


# Loaded once at startup. In production this would refresh periodically
# (e.g. re-pulled from a top-sites source or the backend's own scored DB).
ALL_DOMAINS = load_domain_list()
ALL_DOMAINS_SET = set(ALL_DOMAINS)

# Build the filtered candidate pool used for fuzzy typosquat comparison:
# top-N by rank, generic words removed, deduplicated.
_seen_brands = set()
TYPOSQUAT_CANDIDATES = []
for _domain in ALL_DOMAINS[:TYPOSQUAT_CANDIDATE_LIMIT]:
    _brand = extract_brand(_domain)
    if len(_brand) >= 3 and _brand not in GENERIC_WORD_BLOCKLIST and _brand not in _seen_brands:
        _seen_brands.add(_brand)
        TYPOSQUAT_CANDIDATES.append((_brand, _domain))


def normalize_homoglyphs(domain: str) -> str:
    """
    Replaces digit-lookalikes with their letter equivalents (e.g. paypa1 -> paypal),
    one direction only. This is intentionally one-way: converting letters to digits
    as well would corrupt ordinary domains that legitimately contain those letters
    (e.g. turning "netflix" into "netf1ix" if 'l' were also mapped to '1').
    """
    normalized = domain
    for fake, real in HOMOGLYPH_MAP.items():
        normalized = normalized.replace(fake, real)
    return normalized


def prefilter_score(domain: str) -> dict:
    """
    Returns:
        {
            "risk_score": int 0-100,
            "matched_brand": str or None,
            "matched_domain": str or None,
            "reasons": [str, ...]
        }
    """
    domain = domain.lower().strip()
    reasons = []

    # --- Fast path: exact match against the full known-domains list ---
    if domain in ALL_DOMAINS_SET:
        return {
            "risk_score": 0,
            "matched_brand": extract_brand(domain),
            "matched_domain": domain,
            "reasons": [f"Exact match to a known genuine domain (found in top {len(ALL_DOMAINS)} domains list)."],
        }

    normalized = normalize_homoglyphs(domain)
    domain_label = normalized.split(".")[0]

    # Split on hyphens/underscores into tokens, so a domain like
    # "secure-sbi-verify-login" can be checked token-by-token against brand
    # candidates ("sbi") rather than fuzzy-matching the whole messy string
    # (which is what caused noisy false attributions to unrelated brands
    # that happen to share a substring like "login").
    raw_tokens = [t for t in domain_label.replace("_", "-").split("-") if t]
    candidate_tokens = [domain_label] + [
        t for t in raw_tokens if len(t) >= 3 and t not in SUSPICIOUS_KEYWORDS
    ]
    candidate_tokens = list(dict.fromkeys(candidate_tokens))  # dedupe, preserve order

    best_similarity = 0
    matched_brand = None
    matched_domain = None

    for brand_name, source_domain in TYPOSQUAT_CANDIDATES:
        for token in candidate_tokens:
            # Whole-string ratio only (no partial/substring matching) - this
            # avoids false positives from brand names that merely share a
            # substring with an unrelated token (e.g. "onelogin" matching
            # the "login" fragment inside "arnazon-login").
            similarity = fuzz.ratio(token, brand_name)

            # Exact equality after a hyphen split is a strong, safe signal
            # regardless of brand name length (e.g. token "sbi" == brand "sbi").
            if token == brand_name:
                similarity = 100

            if similarity > best_similarity:
                best_similarity = similarity
                matched_brand = brand_name
                matched_domain = source_domain

    if best_similarity >= 60:
        reasons.append(
            f"Domain name is {best_similarity:.0f}% similar to well-known domain '{matched_domain}' "
            f"but is not the genuine domain."
        )

    keyword_hits = [kw for kw in SUSPICIOUS_KEYWORDS if kw in domain]
    if keyword_hits and best_similarity >= 50:
        reasons.append(f"Contains suspicious keywords often used in phishing: {keyword_hits}")

    if domain.count("-") >= 2:
        reasons.append("Domain contains multiple hyphens, a common phishing obfuscation pattern.")

    # --- Compute risk score ---
    if best_similarity >= 90:
        risk_score = 85
    elif best_similarity >= 75:
        risk_score = 60
    elif best_similarity >= 60:
        risk_score = 30
    else:
        # No meaningful brand similarity. Scale gently with whatever weak
        # similarity was found instead of a flat constant, so genuinely
        # unrelated domains don't all show identical scores.
        risk_score = round(best_similarity * 0.1)

    if keyword_hits and best_similarity >= 50:
        risk_score = min(100, risk_score + 15)
    if domain.count("-") >= 2:
        risk_score = min(100, risk_score + 10)

    if not reasons:
        reasons.append("No strong lexical similarity to known well-known domains.")

    return {
        "risk_score": risk_score,
        "matched_brand": matched_brand if best_similarity >= 60 else None,
        "matched_domain": matched_domain if best_similarity >= 60 else None,
        "reasons": reasons,
    }


if __name__ == "__main__":
    import time

    test_domains = [
        "paypal.com",
        "paypa1-secure-login.com",
        "sbi.co.in",
        "secure-sbi-verify-login.com",
        "randomnewsblog.com",
        "arnazon-login.com",
        "wikipedia.org",
        "github.com",
        "goggle-search.com",
        "netflix-billing-update.com",
    ]
    print(f"Loaded {len(ALL_DOMAINS)} known domains, {len(TYPOSQUAT_CANDIDATES)} typosquat candidates\n")
    start = time.time()
    for d in test_domains:
        print(d, "->", prefilter_score(d))
    elapsed = time.time() - start
    print(f"\nTotal time for {len(test_domains)} checks: {elapsed:.3f}s ({elapsed/len(test_domains)*1000:.1f}ms avg)")
