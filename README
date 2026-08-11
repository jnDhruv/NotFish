# AI/ML-Based Phishing Domain Detection System
### SIH1454 | Technology Bucket: Blockchain & Cybersecurity | Organization: National Technical Research Organisation (NTRO)

---

## 1. What We're Solving

Phishing is the most prevalent attack technique used to compromise users worldwide. Phishing links are distributed via email, SMS, and other mediums, leading users to domains that host login pages imitating genuine target websites. Credentials entered on these pages are compromised, and the pages may also deliver malicious payloads.

**Objective (as specified):** Identify phishing domains from newly registered websites, using open-source databases such as the WHOIS database, which lists newly registered domains. The tool must be automated and use AI/ML to distinguish phishing domains from genuine ones, using:
- **(a)** Backend code / content similarity in web pages, and
- **(b)** Web page image analysis — the more visually similar a new domain's page is to a genuine target's page, the higher its probability score as a lookalike phishing site.

**Our extension of the ask:** Beyond identifying and scoring domains, we deliver the verdict directly to the end user at the point of risk — inside the browser, before a lookalike page can be interacted with — via a lightweight extension backed by a local lookup file, rather than only a backend dashboard the user never sees.

---

## 2. How We Are Doing This

We treat this as a **multi-signal fusion problem**, sourced primarily from **WHOIS newly-registered-domain data** as specified in the problem statement, and delivered through a **two-tier system**: an instant local check in the browser, backed by a deep server-side pipeline for anything the local check can't resolve.

Our approach in one line:

> **WHOIS feed surfaces newly registered domains → cheap pre-filter → deep analysis on survivors (code/content similarity + image similarity) → fuse into one probability score → verdict is pushed straight into the user's browser extension, with a local lookup file resolving future visits to the same domain instantly.**

Three design principles guide this:
1. **WHOIS-first ingestion.** The primary feed is the WHOIS database of newly registered domains, per the problem statement. Certificate Transparency (CT) log monitoring is layered on top as a real-time supplement, since WHOIS registration data can lag actual domain use by hours.
2. **Cascade, don't brute-force.** Cheap lexical/metadata checks run on every domain first; expensive visual/content ML only runs on the subset that looks suspicious — this is what keeps detection time reasonable at scale.
3. **The extension is the output, not an afterthought.** Every design decision downstream of scoring is built around getting the probability score, brand attribution, and evidence in front of the user inside their browser, with the dashboard/API as a secondary channel for analyst review.

---

## 3. Key Features

- **Browser extension (primary output surface)** — checks every visited domain, shows a probability score, brand attribution, and a plain-language reason directly in a popup/banner before the user interacts with the page.
- **Local lookup file** — a signed, periodically-synced Bloom filter of known-malicious and known-safe domains; resolves the majority of visits instantly, with no network call.
- **Cache-miss escalation** — domains not resolved locally are sent to the backend for scoring; the extension shows a "checking..." state, then updates in place once a verdict returns.
- **Automated domain ingestion** — primary: WHOIS/RDAP newly-registered domain lists; supplementary: Certificate Transparency logs for faster real-time capture.
- **Typosquatting & homoglyph detection** — catches character substitution, extra hyphens, brand-name stuffing (e.g. `secure-sbi-login-verify.com`).
- **(b) Web page image analysis** — screenshots the live site and compares it against a reference bank of commonly targeted brands using perceptual hashing + deep visual embeddings; higher visual similarity raises the probability score, as specified.
- **(a) Backend code/content similarity** — compares DOM structure, form fields, favicon hash, and page text against genuine sites to catch cloned login pages.
- **Unified probability score (0–100)** per domain, with a breakdown of contributing signals, shown in the extension UI.
- **Brand attribution** — the extension doesn't just say "phishing," it says "87% likely imitating SBI's login page."
- **False-positive controls** — whitelist for verified/known-legitimate domains baked into the local file, and a requirement that multiple independent signals agree before a high-severity flag is raised.
- **Secondary outputs** — lightweight analyst dashboard, REST API, CSV/JSON export, and email/webhook alerts, for SOC/analyst workflows and system integration.

---

## 4. Architecture and Intelligence System

```
                         ┌───────────────────────────┐
                         │   BROWSER EXTENSION          │  ← primary output surface
                         │   (client-side, per user)    │    probability score + brand
                         └──────────────┬──────────────┘    attribution shown here
                                        │  on navigation
                                        ▼
                         ┌───────────────────────────┐
                         │   LOCAL LOOKUP FILE          │
                         │   (Bloom filter / hashed set, │
                         │   signed, periodically synced)│
                         └──────────────┬──────────────┘
                     match found ◄──────┴──────► no match / low confidence
                          │                              │
                          ▼                              ▼
                 instant verdict                ┌──────────────────────┐
                 shown in extension:              │   DATA INGESTION       │
                 block / warn / allow             │   WHOIS/RDAP (primary),│
                 + score + reason                 │   CT logs (supplement) │
                                                  └──────────┬─────────────┘
                                                             ▼
                                                  ┌──────────────────────┐
                                                  │   PRE-FILTER LAYER     │
                                                  │   lexical distance,    │
                                                  │   homoglyphs, domain   │
                                                  │   age, TLD reputation  │
                                                  └──────────┬─────────────┘
                                                             ▼ (suspicious only)
                                    ┌──────────────────────────────────────────────┐
                                    │              DEEP ANALYSIS LAYER               │
                                    │  ┌───────────────┐   ┌───────────────────┐    │
                                    │  │ (a) Content/   │   │ (b) Image/Visual   │    │
                                    │  │ Code Similarity│   │ Similarity          │    │
                                    │  │ (DOM, favicon, │   │ (screenshots vs    │    │
                                    │  │ text, forms)   │   │ reference brand    │    │
                                    │  │                │   │ bank via pHash+CNN)│    │
                                    │  └───────┬───────┘   └─────────┬──────────┘    │
                                    └──────────┼─────────────────────┼───────────────┘
                                               ▼                     ▼
                                    ┌──────────────────────────────────────────────┐
                                    │           SCORE FUSION / INTELLIGENCE ENGINE   │
                                    │  Weighted ensemble → probability score +       │
                                    │  brand attribution                             │
                                    └──────────┬─────────────────────────────────────┘
                                               ▼
                         ┌────────────────────────────────────────────┐
                         │    OUTPUT LAYER                               │
                         │    → verdict pushed back to requesting        │
                         │      extension instance (primary)             │
                         │    → domain queued into next lookup-file sync │
                         │    → analyst dashboard | REST API |           │
                         │      CSV/JSON export | email/webhook alerts   │
                         │      (secondary, for SOC use)                 │
                         └────────────────────────────────────────────┘
```

**Intelligence system components:**
- **Local lookup file builder**: periodically compiles confirmed-malicious and confirmed-safe domains into a compact, signed structure; publishes delta updates for the extension to pull.
- **Reference Brand Bank**: pre-computed screenshots, DOM fingerprints, and favicon hashes for commonly targeted brands (banks, government portals, e-commerce), refreshed periodically.
- **Classifier model (tabular)**: LightGBM/XGBoost on lexical + metadata features — fast, interpretable, gives an initial risk score.
- **Siamese/CNN visual model**: embeds screenshots and computes similarity against the reference bank — this is the (b) image analysis component.
- **Text/content embedding model**: compares page text and DOM against known legitimate pages — this is the (a) content similarity component.
- **Fusion layer**: combines all signals into a final calibrated probability score, with the breakdown formatted for direct display in the extension popup.

---

## 5. Workflow

1. **Local check (client)** — On navigation, the extension checks the domain against the local lookup file. A match returns an instant verdict — shown as a color-coded banner/badge in the extension with the score and reason — no network call.
2. **Discovery (server)** — In parallel, new domains appear in the WHOIS registration feed (primary, per problem statement); CT log monitoring supplements this for faster capture of domains actively serving content.
3. **Pre-filtering** — Domain name is scored for typosquatting/homoglyph similarity against a brand keyword list; domain age and TLD reputation checked. Low-risk domains are logged and dropped from the deep pipeline.
4. **Rendering & Scraping** — Suspicious domains are rendered with a headless browser; screenshot, HTML/DOM, form fields, and favicon are captured.
5. **Similarity Analysis** — (b) Screenshot compared against the brand reference bank (perceptual hash → CNN embedding for fine-grained cases); (a) DOM/content compared for structural and textual similarity.
6. **Score Fusion** — All signals combined into a single probability score with brand attribution and a breakdown of what triggered the flag.
7. **Verdict delivery (client)** — If a user's extension triggered the lookup (cache miss), the computed verdict is pushed directly back to that session and rendered in the extension UI once ready.
8. **Lookup file sync** — Newly confirmed malicious/safe domains are compiled into the next signed delta update, pulled by all extension instances on their sync interval.
9. **Secondary output & alerting** — Score also pushed to the analyst dashboard; high-risk domains trigger alerts; full data available via API/export for downstream SOC/analyst workflows.
10. **Feedback Loop** — Analyst confirmation/rejection of flagged domains feeds back into model retraining, the whitelist, and the local lookup file, improving accuracy over time.

---

## 6. Output: What the User Sees (Extension UI)

The extension is the primary interface for the tool's output. On every page visit:

| State | What's shown |
|---|---|
| **Safe (local match or low score)** | Small neutral badge on the extension icon; no interruption. |
| **Suspicious (checking)** | Badge shows a "checking" state while a cache-miss request resolves. |
| **High-risk (flagged)** | Full-screen or banner warning before the user can interact with the page, showing: probability score (0–100), the genuine brand it's imitating, and the top contributing signals (e.g. "Visual match: 91% similar to sbi.co.in login page", "Domain registered 2 days ago", "Homoglyph substitution detected"). |
| **User action** | Options to proceed anyway (logged), report as false positive, or view full evidence (side-by-side screenshot comparison) in an expanded panel. |

This same score/evidence payload is what feeds the analyst dashboard and API — the extension and the SOC tooling are two views onto one fusion engine, not two separate systems.

---

## 7. Tech Stack

| Layer | Technology |
|---|---|
| Browser extension | Manifest V3 (Chrome/Edge), WebExtensions API for Firefox; background service worker for lookup + sync; popup/content-script UI for score display |
| Local lookup file | Bloom filter (compact JS/WASM implementation) or hashed domain set, signed + versioned |
| Lookup file distribution | Signed delta updates over HTTPS, pulled on a periodic sync interval |
| Domain feed ingestion | WHOIS/RDAP APIs (primary), CertStream / CT logs (real-time supplement) |
| Task queue / async processing | Redis + Celery |
| Web rendering & scraping | Playwright (headless browser) |
| Lexical/typosquat similarity | python-Levenshtein, jellyfish |
| Visual similarity (b) | OpenCV (perceptual hashing) + pretrained CNN/CLIP embeddings |
| Content/text similarity (a) | Sentence-Transformers (embeddings), DOM diffing |
| Tabular ML model | LightGBM / XGBoost |
| Backend API | FastAPI (Python) |
| Database | PostgreSQL (metadata, scores) + object storage for screenshots |
| Analyst dashboard (secondary) | Streamlit (rapid prototype) or React + Tailwind (production-grade) |
| Alerts | SMTP/webhook integration |
| Deployment | Docker containers, optionally Kubernetes for scale |

---

## 8. Platform Choice

**Recommended: Browser extension (primary output, end-user protection) + lightweight web-based analyst dashboard/REST API (secondary, SOC review), containerized backend, cloud/on-prem deployable.**

Rationale:
- **Output is where the risk is.** The problem statement asks for a tool that identifies lookalike phishing domains; delivering that identification inside the browser, at the moment a user is about to interact with the page, is a more direct fulfilment of the objective than a dashboard the user never sees.
- **WHOIS-grounded, real-time-capable.** WHOIS remains the primary data source as specified; CT logs close the gap between registration and active use so the extension's verdicts stay current.
- **Low-latency, low-cost at scale.** The local lookup file absorbs the overwhelming majority of checks client-side, so the expensive deep-analysis pipeline only runs on genuinely novel domains.
- **Analyst accessibility retained.** SOC teams still get a dashboard to review flagged domains and see evidence — it's a secondary consumer of the same fusion engine, not the primary interface.
- **Deployment flexibility.** Docker-based packaging allows the backend to be deployed on-premise or in a private cloud, satisfying data sovereignty concerns relevant to a national security context.
- **Scalability.** Queue-based architecture (Redis/Celery) allows horizontal scaling of deep-analysis workers independently from the lightweight ingestion/pre-filter layer as domain volume grows.

---

## 9. Development Plan

| Phase | Focus | Deliverables |
|---|---|---|
| **Phase 1** | Data pipeline foundation | WHOIS/RDAP ingestion (primary) working; domains flowing into database; basic lexical/typosquat scorer live |
| **Phase 2** | Local lookup file + extension shell | Bloom filter builder + signed delta-sync mechanism; extension shell (Manifest V3) with badge states and popup UI wired to the local file |
| **Phase 3** | Scraping & reference data | Playwright-based screenshot/DOM scraper; brand reference bank built (~50–100 commonly targeted brands, India-focused: banks, gov.in portals, major e-commerce); CT log supplement added |
| **Phase 4** | Similarity models | (a) content/DOM similarity scoring; (b) perceptual hashing baseline + CNN/embedding-based visual similarity |
| **Phase 5** | Fusion & classification | Tabular classifier (LightGBM/XGBoost) trained on PhishTank/OpenPhish + Tranco data; fusion logic combining all signal scores into final probability |
| **Phase 6** | Extension output + cache-miss path | Full extension warning UI (score, brand attribution, evidence panel); cache-miss escalation and async verdict return; analyst dashboard, REST API, CSV/JSON export, alerting |
| **Phase 7** | Validation & tuning | Test against labeled phishing datasets; tune Bloom filter false-positive rate and sync interval; measure end-to-end latency for both local-hit and cache-miss paths |
| **Phase 8** | Hardening & scale-readiness | Containerization, queue-based scaling, signed lookup-file distribution, feedback loop for continuous model improvement |

**Data sources for training/validation:**
- Phishing: PhishTank, OpenPhish (labeled, freely available feeds)
- Legitimate: Tranco/Majestic Million top-domain lists
- Custom brand reference set built manually for high-priority Indian financial and government targets

---

## 10. Mapping to Evaluation Criteria

- **(e) Probability scores of phishing domains on how close they are to the genuine domain** → the fusion engine combines (a) content/code similarity and (b) image similarity into a single calibrated 0–100 score, shown with a brand-attribution breakdown directly in the extension.
- **(f) Ability to detect new phishing domains in reasonable time** → WHOIS-primary ingestion with CT-log supplementation surfaces new domains quickly; the cascade architecture keeps expensive ML off the critical path; the local lookup file gives instant verdicts for anything already resolved, so users are protected without waiting on a fresh scan for repeat visits.
- **(g) Ease of use and flexibility in output formats** → the extension delivers the primary output at zero effort to the end user (no dashboard to check), while the analyst dashboard, REST API, CSV/JSON export, and email/webhook alerts cover SOC and system-integration use cases.
