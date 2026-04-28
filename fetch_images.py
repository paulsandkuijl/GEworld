import requests
from app.database import SessionLocal
from app.models import Craft, Media

def get_wiki_image(search_query: str) -> str:
    search_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": search_query,
        "utf8": "",
        "format": "json"
    }
    try:
        r = requests.get(search_url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        results = data.get('query', {}).get('search', [])
        if not results:
            return None
            
        title = results[0]['title']
        
        # Now get the main image for this page
        img_params = {
            "action": "query",
            "titles": title,
            "prop": "pageimages",
            "pithumbsize": 800, # Get large thumbnail
            "format": "json"
        }
        r2 = requests.get(search_url, params=img_params, timeout=5)
        pages = r2.json().get('query', {}).get('pages', {})
        for page_id, page_info in pages.items():
            if 'thumbnail' in page_info:
                return page_info['thumbnail']['source']
    except Exception as e:
        print(f"Error fetching for {search_query}: {e}")
        return None
    return None

session = SessionLocal()
print("Starting bulk image fetch for grid cards...")

# Find crafts that don't have any media
crafts = session.query(Craft).all()

for craft in crafts:
    if len(craft.media) > 0:
        continue # Already has an image
        
    print(f"Fetching image for: {craft.name}...")
    img_url = get_wiki_image(f"{craft.name} wing in ground effect")
    if not img_url:
        # Fallback to pure name search
        img_url = get_wiki_image(craft.name)
        
    if img_url:
        media = Media(
            media_type="Image",
            url=img_url,
            is_primary=True,
            attribution="Wikipedia API"
        )
        craft.media.append(media)
        session.commit()
        print(f"[+] Found and saved image: {img_url}")
    else:
        print("[-] No image found.")

session.close()
print("Image fetch complete.")
