"""
Tier 3 deep-analysis stand-in: visual similarity between a candidate site's
screenshot and a reference bank of genuine site screenshots.

For the MVP we use perceptual hashing (imagehash) rather than a full CNN
embedding model:
- It needs no training, no GPU, no model download -> works instantly.
- It genuinely measures visual layout/color/structure similarity, so it
  demonstrates the real concept (not a fake stub).
- It's a documented upgrade path: swap this function's internals for a
  CNN/CLIP embedding + cosine similarity later without changing the API
  contract (still takes two images, returns a 0-100 similarity score).

In production, screenshots would come from a headless browser (Playwright)
rendering the live candidate site. For this MVP, screenshots are pre-saved
images in reference_images/ and test_images/ so the demo doesn't depend on
live browser automation or network access.
"""

import os
import imagehash
from PIL import Image

REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "reference_images")


def load_reference_bank() -> dict:
    """Loads all reference (genuine) site screenshots and their perceptual hashes."""
    bank = {}
    if not os.path.isdir(REFERENCE_DIR):
        return bank
    for fname in os.listdir(REFERENCE_DIR):
        if fname.lower().endswith((".png", ".jpg", ".jpeg")):
            brand_name = os.path.splitext(fname)[0]  # e.g. "paypal_genuine"
            path = os.path.join(REFERENCE_DIR, fname)
            bank[brand_name] = imagehash.phash(Image.open(path))
    return bank


# Loaded once at startup; in production this would refresh periodically
# as the reference brand bank is updated.
REFERENCE_BANK = load_reference_bank()


def visual_similarity_score(candidate_image_path: str) -> dict:
    """
    Compares a candidate screenshot against every image in the reference bank.
    Returns the closest match and a 0-100 similarity score.

    Perceptual hash distance is a Hamming distance between hash bits (0 = identical,
    higher = more different). We convert that into an intuitive 0-100 similarity score.
    """
    if not os.path.exists(candidate_image_path):
        return {"similarity_score": 0, "closest_match": None, "error": "image not found"}

    candidate_hash = imagehash.phash(Image.open(candidate_image_path))

    best_match = None
    best_distance = None

    for brand_name, ref_hash in REFERENCE_BANK.items():
        distance = candidate_hash - ref_hash  # Hamming distance, phash is 64-bit -> 0-64
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_match = brand_name

    if best_distance is None:
        return {"similarity_score": 0, "closest_match": None, "error": "reference bank empty"}

    # Convert Hamming distance (0-64, lower = more similar) to a 0-100 similarity score
    similarity_score = max(0, round((1 - best_distance / 64) * 100))

    return {
        "similarity_score": similarity_score,
        "closest_match": best_match,
        "hash_distance": int(best_distance),  # cast from numpy.int64 for JSON serialization
    }


if __name__ == "__main__":
    test_dir = os.path.join(os.path.dirname(__file__), "test_images")
    for fname in os.listdir(test_dir):
        path = os.path.join(test_dir, fname)
        print(fname, "->", visual_similarity_score(path))
