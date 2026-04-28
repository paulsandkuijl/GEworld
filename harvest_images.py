"""
Image Harvester v2 for Ground Effect World
- Uses Wikipedia thumbnail API (avoids 429 rate limits on full-res)
- Handles Unicode safely
- Adds GEC-specific search hints for ambiguous craft names
- Downloads to app/static/images/<craft_id>.jpg
- Updates Media records in DB
"""

import os
import sys
import re
import time
import requests
from app.database import SessionLocal
from app.models import Craft, Media

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

IMAGE_DIR = os.path.join("app", "static", "images")
os.makedirs(IMAGE_DIR, exist_ok=True)

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "GroundEffectWorldBot/2.0 (educational project; polite crawl)"
}

# Disambiguation hints: craft name -> better Wikipedia search term
SEARCH_HINTS = {
    "SM-1": "Alekseyev SM-1 ekranoplan",
    "SM-2": "Alekseyev SM-2 ekranoplan",
    "SM-3": "Alekseyev SM-3 ekranoplan",
    "SM-4": "Alekseyev SM-4 ekranoplan",
    "SM-5": "Alekseyev SM-5 ekranoplan",
    "SM-6": "Alekseyev SM-6 ekranoplan",
    "SM-8": "Alekseyev SM-8 ekranoplan",
    "Volga-2": "Volga-2 ekranoplan",
    "Orion-14": "Orion-14 ekranoplan",
    "Orion-20": "Orion-20 ekranoplan",
    "Strizh": "Strizh ground effect",
    "Aquaglide": "Aquaglide ground effect vehicle",
    "Hanno-1": "Hanno Fischer ground effect",
    "Regent Viceroy": "Regent Craft Viceroy seaglider",
    "Regent Monarch": "Regent Craft Monarch seaglider",
}

# Filename patterns indicating non-craft images
REJECT_PATTERNS = re.compile(
    r"(flag|icon|logo|map|coat.of.arms|emblem|seal|badge|insignia|silhouette"
    r"|diagram|schematic|route|location|portrait|signature|stamp"
    r"|crest|patch|roundel|symbol|pictogram|blank|stub|commons-logo"
    r"|question.book|wikidata|edit.pencil|ambox|text.document|folder"
    r"|Crystal.Clear|nuvola|disambig|wikiquote|wikisource|padlock)",
    re.IGNORECASE
)

GOOD_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def get_wiki_page_title(craft_name: str) -> str | None:
    """Search Wikipedia for the best matching page title."""
    search_term = SEARCH_HINTS.get(craft_name, craft_name)
    try:
        r = requests.get(WIKI_API, params={
            "action": "query", "list": "search",
            "srsearch": search_term, "srlimit": "3",
            "utf8": "", "format": "json"
        }, headers=HEADERS, timeout=10)
        results = r.json().get("query", {}).get("search", [])
        if results:
            return results[0]["title"]
    except Exception as e:
        print(f"    [-] Search error: {e}")
    return None


def get_page_thumbnail(title: str, width: int = 1200) -> str | None:
    """Get the main page thumbnail at specified width. Fast and rate-limit-safe."""
    try:
        r = requests.get(WIKI_API, params={
            "action": "query", "titles": title,
            "prop": "pageimages", "pithumbsize": width,
            "format": "json"
        }, headers=HEADERS, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            if thumb.get("source"):
                return thumb["source"]
    except Exception as e:
        print(f"    [-] Thumbnail fetch error: {e}")
    return None


def get_all_page_images(title: str) -> list[dict]:
    """Fallback: get all images on a page with metadata."""
    images = []
    try:
        r = requests.get(WIKI_API, params={
            "action": "query", "titles": title,
            "prop": "images", "imlimit": "50",
            "format": "json"
        }, headers=HEADERS, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        img_titles = []
        for page in pages.values():
            for img in page.get("images", []):
                img_titles.append(img["title"])

        if not img_titles:
            return images

        # Resolve URLs in chunks
        for i in range(0, len(img_titles), 20):
            chunk = "|".join(img_titles[i:i+20])
            r2 = requests.get(WIKI_API, params={
                "action": "query", "titles": chunk,
                "prop": "imageinfo", "iiprop": "url|size",
                "iiurlwidth": "1200",  # Request thumbnail URL
                "format": "json"
            }, headers=HEADERS, timeout=10)
            for page in r2.json().get("query", {}).get("pages", {}).values():
                ii = page.get("imageinfo", [{}])[0]
                # Prefer the resized thumburl over the full url
                url = ii.get("thumburl") or ii.get("url", "")
                w = ii.get("thumbwidth") or ii.get("width", 0)
                h = ii.get("thumbheight") or ii.get("height", 0)
                if url:
                    images.append({
                        "title": page.get("title", ""),
                        "url": url, "width": w, "height": h
                    })
            time.sleep(0.3)
    except Exception as e:
        print(f"    [-] Image list error: {e}")
    return images


def score_image(img: dict) -> float:
    """Score an image. Higher = better. Returns -1 to reject."""
    title = img["title"].lower()
    url = img["url"].lower()
    ext = os.path.splitext(url.split("?")[0].split("/")[-1])[1]

    if ext not in GOOD_EXT:
        return -1
    if REJECT_PATTERNS.search(title):
        return -1
    if img["width"] < 200 or img["height"] < 150:
        return -1

    area = img["width"] * img["height"]
    score = float(area)

    # Landscape bonus (craft photos are usually wide)
    if img["width"] > img["height"]:
        score *= 1.3
    # JPG bonus (usually real photos)
    if ext in {".jpg", ".jpeg"}:
        score *= 1.2

    return score


def download_image(url: str, dest_path: str) -> bool:
    """Download image. Returns True on success."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size = os.path.getsize(dest_path)
        if size < 3000:
            os.remove(dest_path)
            return False
        return True
    except Exception as e:
        print(f"    [-] Download failed: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def process_craft(craft: Craft, db) -> bool:
    """Find, download, and attach the best image for a craft."""
    print(f"\n[{craft.id:03d}] {craft.name}")

    # Check if we already have a local image
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        existing = os.path.join(IMAGE_DIR, f"{craft.id}{ext}")
        if os.path.exists(existing) and os.path.getsize(existing) > 3000:
            static_url = f"/static/images/{craft.id}{ext}"
            # Check if DB already points here
            if craft.media and any(m.url == static_url for m in craft.media):
                print(f"    [*] Already done, skipping.")
                return True

    # 1. Find Wikipedia page
    title = get_wiki_page_title(craft.name)
    if not title:
        print("    [-] No Wikipedia page found.")
        return False
    print(f"    [*] Wiki page: {title}")

    # 2. Try page thumbnail first (fastest, no rate limit issues)
    best_url = get_page_thumbnail(title, 1200)
    source = "thumbnail"

    # 3. If no thumbnail, fall back to scoring all page images
    if not best_url:
        print("    [*] No thumbnail, scanning all page images...")
        images = get_all_page_images(title)
        scored = [(score_image(img), img) for img in images]
        scored = [(s, img) for s, img in scored if s > 0]
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            best_url = scored[0][1]["url"]
            source = "scored"
        else:
            print("    [-] No usable image found.")
            return False

    print(f"    [+] Best ({source}): ...{best_url[-50:]}")

    # 4. Download
    save_ext = ".jpg"
    raw_ext = os.path.splitext(best_url.split("?")[0].split("/")[-1])[1].lower()
    if raw_ext in GOOD_EXT:
        save_ext = raw_ext

    local_filename = f"{craft.id}{save_ext}"
    local_path = os.path.join(IMAGE_DIR, local_filename)
    static_url = f"/static/images/{local_filename}"

    if not os.path.exists(local_path):
        ok = download_image(best_url, local_path)
        if not ok:
            return False
        print(f"    [+] Saved: {local_path} ({os.path.getsize(local_path):,} bytes)")
    else:
        print(f"    [*] Already downloaded: {local_path}")

    # 5. Update DB
    for m in list(craft.media):
        db.delete(m)
    db.flush()

    new_media = Media(
        media_type="Image",
        url=static_url,
        is_primary=True,
        attribution=f"Wikipedia - {title}",
        description="Primary craft photo"
    )
    craft.media.append(new_media)
    db.commit()
    print(f"    [+] DB updated: {static_url}")
    return True


def main():
    print("=" * 60)
    print(" Ground Effect World - Image Harvester v2")
    print("=" * 60)

    db = SessionLocal()
    crafts = db.query(Craft).order_by(Craft.id).all()
    total = len(crafts)
    print(f"\nProcessing {total} crafts...\n")

    success = 0
    failed = []
    for i, craft in enumerate(crafts, 1):
        ok = process_craft(craft, db)
        if ok:
            success += 1
        else:
            failed.append(craft.name)
        # Progress line
        print(f"    --- Progress: {i}/{total} ({success} images found) ---")
        time.sleep(0.8)  # politeness delay

    db.close()

    print(f"\n{'=' * 60}")
    print(f" Done! {success}/{total} crafts have local images.")
    if failed:
        print(f"\n Missing images ({len(failed)}):")
        for name in failed:
            print(f"   - {name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
