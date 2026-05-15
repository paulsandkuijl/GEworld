import os
import datetime
import requests
import os
import uuid
import json
import time
import concurrent.futures
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from typing import Optional, List
from openai import OpenAI
from googlesearch import search as google_search

# Import our DB models
from app.database import get_session, engine
from app.models import Craft, Specification, Engine, Source, Media, Milestone, Base

# --------------------------------------------------------------------------------
# CRAWLER STATE TRACKING
# --------------------------------------------------------------------------------
STATE_FILE = "crawler_state.json"

def update_crawler_state(craft_name="None", status="Idle", progress=0, ai_part=0, ai_total=0, ai_time=0):
    try:
        session = get_session()
        queue_count = session.query(Craft).filter(Craft.status == 'In Database Queue').count()
        processed_count = session.query(Craft).filter(Craft.status == 'Processed').count()
        session.close()

        state = {
            "current_craft": craft_name,
            "status": status,
            "progress": progress,
            "queue_remaining": queue_count,
            "total_processed": processed_count,
            "ai_model": "llama3.2",
            "ai_part": ai_part,
            "ai_total": ai_total,
            "ai_last_time_s": ai_time,
            "last_updated": datetime.datetime.now().isoformat()
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[-] Failed to update state file: {e}")

# --------------------------------------------------------------------------------
# PYDANTIC SCHEMAS FOR LLM EXPECTED OUTPUT
# --------------------------------------------------------------------------------
class SpecificationSchema(BaseModel):
    length_m: Optional[float] = None
    beam_m: Optional[float] = None
    wingspan_m: Optional[float] = None
    height_m: Optional[float] = None
    empty_weight_kg: Optional[float] = None
    max_takeoff_weight_kg: Optional[float] = None
    payload_capacity_kg: Optional[float] = None
    max_speed_kmh: Optional[float] = None
    cruise_speed_kmh: Optional[float] = None
    range_km: Optional[float] = None
    ground_effect_altitude_m: Optional[float] = None
    service_ceiling_m: Optional[float] = None
    wing_configuration: Optional[str] = None
    hull_material: Optional[str] = None
    crew_capacity: Optional[int] = None
    passenger_capacity: Optional[int] = None

class EngineSchema(BaseModel):
    engine_name: Optional[str] = None
    engine_type: Optional[str] = None
    quantity: Optional[int] = 1
    thrust_kn: Optional[float] = None
    power_kw: Optional[float] = None

class MediaSchema(BaseModel):
    media_type: Optional[str] = Field("Image", description="Image, Video, Document")
    url: Optional[str] = None
    attribution: Optional[str] = None
    description: Optional[str] = None

class MilestoneSchema(BaseModel):
    year: int
    event_title: str
    event_description: Optional[str] = None

class CraftExtraction(BaseModel):
    found_craft: bool = Field(default=True, description="True if the text discusses a valid ground effect craft.")
    data_confidence_score: float = Field(default=1.0, description="0.0 to 1.0 confidence that this craft strictly derives primary lift from aerodynamic winged ground effect (exclude F1 cars, helicopters, ACV, SES, hovercrafts).")
    
    name: Optional[str] = Field(None, description="The primary name of the craft.")
    alternative_names: Optional[str] = None
    designer: Optional[str] = None
    manufacturer: Optional[str] = None
    country_of_origin: Optional[str] = None
    year_introduced: Optional[int] = None
    operational_era: Optional[str] = None
    
    status: Optional[str] = Field(None, description="e.g., Historical, Active, Concept, Cancelled")
    craft_type: Optional[str] = Field(None, description="e.g., WIG, Ekranoplan, PAR, Concept")
    
    description_history: Optional[str] = None
    operational_history: Optional[str] = None
    known_accidents: Optional[str] = None
    current_location: Optional[str] = None
    
    specifications: Optional[SpecificationSchema] = None
    engines: Optional[List[EngineSchema]] = Field(default_factory=list)
    media: Optional[List[MediaSchema]] = Field(default_factory=list)
    milestones: Optional[List[MilestoneSchema]] = Field(default_factory=list)


# --------------------------------------------------------------------------------
# CORE CRAWLER LOGIC
# --------------------------------------------------------------------------------
def perform_search(query: str, max_results: int = 3) -> list[dict]:
    # Add context to search if the query is too short or likely generic
    search_query = query
    if len(query) < 5 or query.isdigit():
        search_query = f"{query} ground effect craft ekranoplan"
    
    print(f"[*] Searching Wikipedia for: '{search_query}'")
    try:
        headers = {'User-Agent': 'GroundEffectCrawler/2.0'}
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": search_query,
            "utf8": "",
            "format": "json"
        }
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        urls = []
        search_results = data.get('query', {}).get('search', [])
        
        for item in search_results:
            title = item['title']
            snippet = item.get('snippet', '').lower()
            
            # Simple heuristic: skip results that are obviously not about vehicles
            # if we have multiple results to choose from.
            bad_keywords = ["bridge", "tunnel", "highway", "river", "constellation", "galaxy", "film", "song"]
            if any(bk in title.lower() or bk in snippet for bk in bad_keywords):
                if len(urls) < max_results: # Still include if we have nothing else, but maybe skip?
                    continue

            title_formatted = title.replace(' ', '_')
            urls.append({'href': f"https://en.wikipedia.org/wiki/{title_formatted}", 'title': title})
            
            if len(urls) >= max_results:
                break
                
        return urls
    except Exception as e:
        print(f"[-] Search failed: {e}")
        return []

def perform_extended_search(query: str, max_results: int = 5) -> list[str]:
    print(f"[*] Performing extended web search for: '{query}'")
    urls = []
    try:
        search_results = google_search(query, num_results=max_results * 2, sleep_interval=1)
        for url in search_results:
            if "wikipedia.org" not in url:
                urls.append(url)
            if len(urls) >= max_results:
                break
    except Exception as e:
        print(f"[-] Extended search failed: {e}")
    return urls

def scrape_url_text(url: str) -> str:
    print(f"[*] Scraping URL: {url}...")
    try:
        headers = {
            # Mimic a real browser so sites don't block the request
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        # Auto-detect encoding to handle non-English sites
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove boilerplate noise that isn't content
        noise_tags = [
            "script", "style", "nav", "footer", "header", "aside",
            "noscript", "iframe", "form", "button", "svg"
        ]
        for tag in soup(noise_tags):
            tag.decompose()

        # Remove common ad/cookie/comment class names
        for cls in ["cookie", "banner", "advertisement", "popup", "sidebar", "comment", "share", "social", "promo"]:
            for el in soup.find_all(class_=lambda c: c and cls in c.lower()):
                el.decompose()

        # Prefer the main article content if it exists
        main_content = soup.find('article') or soup.find('main') or soup.find(id='content') or soup.find(id='bodyContent') or soup.body
        
        image_urls = []
        if main_content:
            for img in main_content.find_all('img'):
                src = img.get('src')
                if src and not src.startswith('data:') and 'icon' not in src.lower() and 'logo' not in src.lower() and 'svg' not in src.lower():
                    if src.startswith('//'): src = 'https:' + src
                    elif src.startswith('/'): src = 'https://en.wikipedia.org' + src 
                    image_urls.append(src)
        
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)

        # Collapse excessive whitespace
        import re
        text = re.sub(r'\s{2,}', ' ', text)
        
        if image_urls:
            unique_images = list(dict.fromkeys(image_urls))[:5]
            text += "\n\n--- RELEVANT IMAGE URLS ---\n" + "\n".join(unique_images)
            
        print(f"[*] Scraped {len(text)} characters of clean text.")
        return text[:15000]  # Allow more text since we will chunk it now
    except Exception as e:
        print(f"[-] Failed to scrape {url}: {e}")
        return ""

def extract_facts_from_chunk(text: str, client: OpenAI, craft_name: str, part_num: int, total_parts: int) -> list:
    """Map step: Extract raw facts from a single chunk of text."""
    prompt = f"""
    Extract technical facts about the Wing-in-Ground (WIG) craft "{craft_name}" from the TEXT below.
    Focus on:
    - Specifications (weight, dimensions, speed, range)
    - Engines (names, types, numbers)
    - History, Milestones, and Operational Status
    - Media descriptions or URLs
    
    Return a JSON object with a single key "facts" which is a list of strings. 
    Each string should be a single, concise technical fact.
    If no relevant facts are found, return an empty list.
    
    TEXT:
    {text}
    """
    
    try:
        completion = client.chat.completions.create(
            model="llama3.2:1b",
            messages=[
                {"role": "system", "content": "You are a technical data extractor. Output ONLY a JSON object with a 'facts' list. No preamble. If no specific technical facts about the craft are found, return {'facts': []}."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            timeout=180
        )
        data = json.loads(completion.choices[0].message.content)
        return data.get("facts", [])
    except Exception as e:
        print(f"[-] [Map] Failed for part {part_num}: {e}")
        return []

def consolidate_facts(facts: list, client: OpenAI, craft_name: str) -> Optional[CraftExtraction]:
    """Reduce step: Consolidate all extracted facts into the final schema."""
    if not facts:
        return None
        
    facts_text = "\n".join([f"- {f}" for f in facts])
    
    prompt = f"""
    You are a technical data architect. Consolidate the following technical facts about the Wing-in-Ground (WIG) craft "{craft_name}" into the structured JSON schema provided.
    
    FACTS COLLECTED FROM RESEARCH:
    {facts_text}
    
    You MUST output valid, parsable JSON matching this EXACT template. 
    If a value is unknown, use null for numbers or "Unknown" for strings.
    
    {{
        "found_craft": true,
        "data_confidence_score": 1.0,
        "name": "{craft_name}",
        "alternative_names": "Unknown",
        "designer": "Unknown",
        "manufacturer": "Unknown",
        "country_of_origin": "Unknown",
        "year_introduced": null,
        "operational_era": "Unknown",
        "status": "Unknown",
        "craft_type": "Ekranoplan",
        "description_history": "Unknown",
        "operational_history": "Unknown",
        "known_accidents": "Unknown",
        "current_location": "Unknown",
        "specifications": {{
            "length_m": null, "beam_m": null, "wingspan_m": null, "height_m": null,
            "empty_weight_kg": null, "max_takeoff_weight_kg": null, "payload_capacity_kg": null,
            "max_speed_kmh": null, "cruise_speed_kmh": null, "range_km": null,
            "ground_effect_altitude_m": null, "service_ceiling_m": null,
            "wing_configuration": null, "hull_material": null, "crew_capacity": null, "passenger_capacity": null
        }},
        "engines": [],
        "media": [],
        "milestones": []
    }}
    """
    
    try:
        completion = client.chat.completions.create(
            model="llama3.2",
            messages=[
                {"role": "system", "content": "You are a perfect JSON generator. Output only the requested JSON object."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            timeout=180
        )
        return CraftExtraction.model_validate_json(completion.choices[0].message.content)
    except Exception as e:
        print(f"[-] [Reduce] Failed: {e}")
        return None

def merge_extractions(base: CraftExtraction, new: CraftExtraction) -> CraftExtraction:
    """Merges a new extraction into the base one, preferring non-null/non-placeholder values."""
    if not base: return new
    if not new: return base

    # Simple fields
    for field in ['alternative_names', 'designer', 'manufacturer', 'country_of_origin', 'operational_era', 'status', 'craft_type', 'current_location']:
        val = getattr(new, field)
        if val and val not in [None, "Unknown", "null", ""]:
            setattr(base, field, val)
    
    # Large text fields (concatenate if different)
    for field in ['description_history', 'operational_history', 'known_accidents']:
        val = getattr(new, field)
        if val and val not in [None, "null", ""] and val not in getattr(base, field):
            old_val = getattr(base, field) or ""
            setattr(base, field, (old_val + "\n\n" + val).strip())

    # Specifications
    if new.specifications:
        if not base.specifications:
            base.specifications = new.specifications
        else:
            for field, val in new.specifications.model_dump().items():
                if val is not None:
                    setattr(base.specifications, field, val)

    # Lists (append if unique)
    def append_unique(base_list, new_list, key_attr):
        existing_keys = {getattr(i, key_attr) for i in base_list if hasattr(i, key_attr)}
        for item in new_list:
            if hasattr(item, key_attr) and getattr(item, key_attr) not in existing_keys:
                base_list.append(item)
            elif not hasattr(item, key_attr):
                base_list.append(item)

    append_unique(base.engines, new.engines, 'engine_name')
    append_unique(base.media, new.media, 'url')
    append_unique(base.milestones, new.milestones, 'event_title')

    return base

def ingest_to_db(extraction: CraftExtraction, url: str, existing_craft: Craft, reconcile: bool = False) -> list:
    session = get_session()
    # We must merge it into the current session to update it
    craft = session.merge(existing_craft)

    # Force the name so the script guarantees it ties back correctly
    craft_name = extraction.name or existing_craft.name
    print(f"[+] UPDATING: Populating seeded craft '{craft_name}' with new AI extraction...")
    
    conflicts = []

    def check_field(obj, field_name, new_val, label):
        old_val = getattr(obj, field_name, None)
        # Skip if crawler found nothing new
        if new_val is None or str(new_val).strip() == "":
            return
        
        # If DB is empty or values match, automatically update
        if old_val is None or str(old_val).strip() == "" or old_val == new_val:
            setattr(obj, field_name, new_val)
        else:
            # If there's a difference and reconcile is requested, flag it
            if reconcile:
                conflicts.append({
                    "field": field_name,
                    "label": label,
                    "db_value": old_val,
                    "crawler_value": new_val
                })
            else:
                setattr(obj, field_name, new_val)

    # Update base fields
    check_field(craft, "alternative_names", extraction.alternative_names, "Alternative Names")
    check_field(craft, "designer", extraction.designer, "Designer")
    check_field(craft, "manufacturer", extraction.manufacturer, "Manufacturer")
    check_field(craft, "country_of_origin", extraction.country_of_origin, "Country of Origin")
    check_field(craft, "year_introduced", extraction.year_introduced, "Year Introduced")
    check_field(craft, "operational_era", extraction.operational_era, "Operational Era")
    check_field(craft, "status", extraction.status, "Status")
    check_field(craft, "craft_type", extraction.craft_type, "Craft Type")
    check_field(craft, "description_history", extraction.description_history, "Description/History")
    check_field(craft, "operational_history", extraction.operational_history, "Operational History")
    check_field(craft, "known_accidents", extraction.known_accidents, "Known Accidents")
    check_field(craft, "current_location", extraction.current_location, "Current Location")
    
    # Update confidence score
    if extraction.data_confidence_score:
        craft.data_confidence_score = extraction.data_confidence_score
    
    if extraction.specifications:
        if not craft.specifications:
            craft.specifications = Specification()
            
        spec = craft.specifications
        ext_spec = extraction.specifications
        check_field(spec, "length_m", ext_spec.length_m, "Length (m)")
        check_field(spec, "beam_m", ext_spec.beam_m, "Beam (m)")
        check_field(spec, "wingspan_m", ext_spec.wingspan_m, "Wingspan (m)")
        check_field(spec, "height_m", ext_spec.height_m, "Height (m)")
        check_field(spec, "empty_weight_kg", ext_spec.empty_weight_kg, "Empty Weight (kg)")
        check_field(spec, "max_takeoff_weight_kg", ext_spec.max_takeoff_weight_kg, "Max Takeoff Weight (kg)")
        check_field(spec, "payload_capacity_kg", ext_spec.payload_capacity_kg, "Payload Capacity (kg)")
        check_field(spec, "max_speed_kmh", ext_spec.max_speed_kmh, "Max Speed (km/h)")
        check_field(spec, "cruise_speed_kmh", ext_spec.cruise_speed_kmh, "Cruise Speed (km/h)")
        check_field(spec, "range_km", ext_spec.range_km, "Range (km)")
        check_field(spec, "ground_effect_altitude_m", ext_spec.ground_effect_altitude_m, "Ground Effect Altitude (m)")
        check_field(spec, "service_ceiling_m", ext_spec.service_ceiling_m, "Service Ceiling (m)")
        check_field(spec, "wing_configuration", ext_spec.wing_configuration, "Wing Configuration")
        check_field(spec, "hull_material", ext_spec.hull_material, "Hull Material")
        check_field(spec, "crew_capacity", ext_spec.crew_capacity, "Crew Capacity")
        check_field(spec, "passenger_capacity", ext_spec.passenger_capacity, "Passenger Capacity")
        
    for e in extraction.engines:
        craft.engines.append(Engine(
            engine_name=e.engine_name, engine_type=e.engine_type,
            quantity=e.quantity, thrust_kn=e.thrust_kn, power_kw=e.power_kw
        ))
        
    def download_and_save_image(url: str, dest_dir: str = "app/static/media") -> Optional[str]:
        if not url.startswith("http"): return None
        try:
            os.makedirs(dest_dir, exist_ok=True)
            resp = requests.get(url, stream=True, timeout=10)
            resp.raise_for_status()
            parsed = urlparse(url)
            ext = os.path.splitext(parsed.path)[1]
            if not ext:
                content_type = resp.headers.get('Content-Type', '')
                if 'image/jpeg' in content_type: ext = '.jpg'
                elif 'image/png' in content_type: ext = '.png'
                elif 'image/webp' in content_type: ext = '.webp'
                else: ext = '.jpg'
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(dest_dir, filename)
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return f"/static/media/{filename}"
        except Exception as e:
            print(f"[-] Failed to download image {url}: {e}")
            return None
            
    for m in extraction.media:
        if m.url:
            local_url = download_and_save_image(m.url)
            if local_url:
                craft.media.append(Media(
                    media_type=m.media_type, url=local_url, attribution=m.attribution, description=m.description
                ))
                break  # Only keep one successfully downloaded image
            
    for ms in extraction.milestones:
        craft.milestones.append(Milestone(
            year=ms.year, event_title=ms.event_title, event_description=ms.event_description
        ))
        
    craft.sources.append(Source(url=url, source_type="Primary", scrape_date=datetime.datetime.now()))

    session.commit()
    print(f"[+] Successfully saved '{craft.name}' fully mapped to expanded schema!")
    session.close()
    return conflicts

def needs_more_info(extraction: CraftExtraction) -> bool:
    if not extraction: return True
    m = 0
    if not extraction.description_history or extraction.description_history == "Unknown": m += 1
    if not extraction.manufacturer or extraction.manufacturer == "Unknown": m += 1
    if not extraction.specifications or not extraction.specifications.length_m: m += 1
    if not extraction.specifications or not extraction.specifications.max_speed_kmh: m += 1
    # If 2 or more key fields are missing, we consider it missing info
    return m >= 2

def main():
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        
    print("\n============= GROUND EFFECT CRAFT AI CRAWLER =============")
    # max_retries=0 prevents the client from silently re-issuing hung requests
    client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama', max_retries=0)

    # On startup, reset any craft that was abandoned mid-extraction so it gets
    # re-queued rather than skipped permanently.
    print("[*] Checking for abandoned in-progress extractions...")
    try:
        session = get_session()
        import datetime as _dt
        # Any craft still 'In Database Queue' with a recent state file entry
        # may be the one that was hanging. Re-queue it by leaving status as-is;
        # the loop below will simply pick it up again and retry.
        stuck_count = session.query(Craft).filter(Craft.status == 'In Database Queue').count()
        session.close()
        print(f"[*] {stuck_count} craft(s) remain in the queue — resuming.")
    except Exception as e:
        print(f"[-] Startup check failed: {e}")

    while True:
        update_crawler_state(status="Checking queue...", progress=0)
        session = get_session()
        target_craft = session.query(Craft).filter(Craft.status == 'In Database Queue').first()
        session.close()
        
        if not target_craft:
            print("No pending crafts in queue. Sleeping for 60 seconds...")
            update_crawler_state(status="Idle (Queue Empty)", progress=100)
            time.sleep(60)
            continue
            
        # Strictly use base name to rely natively on Wiki's title match algorithm
        base_name = target_craft.name.split(" (")[0]
        query = base_name
        print(f"\n>>>> PROCESSING PENDING TARGET: {query}")
        update_crawler_state(craft_name=query, status="Searching Wikipedia...", progress=10)
        
        results = perform_search(query, max_results=1)
        if not results:
            print("[-] No search results found.")
            session = get_session()
            craft = session.query(Craft).get(target_craft.id)
            if craft:
                craft.status = 'No Results Found'
                session.commit()
            session.close()
            update_crawler_state(craft_name=query, status="No Results Found", progress=0)
            continue
            
        url = results[0].get('href')
        update_crawler_state(craft_name=query, status=f"Scraping {url}...", progress=30)
        text = scrape_url_text(url)
        
        # Validation: Check if the text actually mentions relevant keywords
        wig_keywords = ["ground effect", "ekranoplan", "wing-in-ground", "wig", "aerodynamic lift", "surface effect"]
        if not any(kw in text.lower() for kw in wig_keywords) and len(results) > 1:
            print(f"[*] Primary result {url} seems irrelevant. Trying secondary...")
            url = results[1].get('href')
            update_crawler_state(craft_name=query, status=f"Scraping secondary {url}...", progress=35)
            text = scrape_url_text(url)

        if len(text) < 200:
            print("[-] Scraped text was too short...")
            session = get_session()
            craft = session.query(Craft).get(target_craft.id)
            if craft:
                craft.status = 'Insufficient Text'
                session.commit()
            session.close()
            update_crawler_state(craft_name=query, status="Insufficient Text Content", progress=0)
            continue
            
        # Divide text into 12000-character chunks for Map-Reduce
        chunk_size = 12000
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        
        # Pre-filter chunks to only send those with relevant keywords
        def is_relevant_chunk(c: str) -> bool:
            keywords = ["engine", "speed", "kg", "meters", "designed", "built", "length", "weight", "payload", "wing", "range", "knot", "km/h", "mph"]
            return any(kw in c.lower() for kw in keywords)

        valid_chunks = [c for c in chunks if is_relevant_chunk(c)]
        if not valid_chunks:
            valid_chunks = chunks[:2] # Fallback
            
        all_facts = []
        for idx, chunk in enumerate(valid_chunks):
            part_num = idx + 1
            update_crawler_state(
                craft_name=query, 
                status=f"AI Fact Mapping (Part {part_num}/{len(valid_chunks)})...", 
                progress=60 + int((idx / len(valid_chunks)) * 20),
                ai_part=part_num,
                ai_total=len(valid_chunks)
            )
            
            start_t = time.time()
            chunk_facts = extract_facts_from_chunk(chunk, client, target_craft.name, part_num, len(valid_chunks))
            duration = round(time.time() - start_t, 1)
            
            if chunk_facts:
                all_facts.extend(chunk_facts)
                update_crawler_state(
                    craft_name=query, 
                    status=f"Map Part {part_num} OK", 
                    progress=60 + int((part_num / len(valid_chunks)) * 20),
                    ai_part=part_num,
                    ai_total=len(valid_chunks),
                    ai_time=duration
                )
            else:
                print(f"[-] No facts found in part {part_num}")

        if all_facts:
            update_crawler_state(craft_name=query, status="Consolidating Facts (Reduce)...", progress=85)
            final_extraction = consolidate_facts(all_facts, client, target_craft.name)
        else:
            final_extraction = None
            
        # --- EXTENDED SEARCH FOR MISSING INFO ---
        search_query = f"{query} ground effect craft ekranoplan"
        if needs_more_info(final_extraction):
            update_crawler_state(craft_name=query, status="Fetching additional sites...", progress=86)
            extended_urls = perform_extended_search(search_query, max_results=5)
            for idx, ext_url in enumerate(extended_urls):
                update_crawler_state(craft_name=query, status=f"Scraping extra site {idx+1}/{len(extended_urls)}...", progress=86 + idx)
                ext_text = scrape_url_text(ext_url)
                if len(ext_text) < 200: continue
                
                # We limit extra sites to chunks that have keywords
                ext_chunks = [ext_text[i:i + chunk_size] for i in range(0, len(ext_text), chunk_size)]
                valid_ext_chunks = [c for c in ext_chunks if is_relevant_chunk(c)][:3] # max 3 chunks
                
                ext_facts = []
                for idx, chunk in enumerate(valid_ext_chunks):
                    facts = extract_facts_from_chunk(chunk, client, target_craft.name, idx+1, len(valid_ext_chunks))
                    if facts: ext_facts.extend(facts)
                    
                if ext_facts:
                    ext_extraction = consolidate_facts(ext_facts, client, target_craft.name)
                    if ext_extraction:
                        if not final_extraction:
                            final_extraction = ext_extraction
                        else:
                            final_extraction = merge_extractions(final_extraction, ext_extraction)
                            
                        # If we have enough info now, we can stop scraping additional sites early
                        if not needs_more_info(final_extraction):
                            print("[+] Sufficient info gathered from extended search. Stopping extra scraping.")
                            break
        
        if final_extraction:
            update_crawler_state(craft_name=query, status="Saving to Database...", progress=90, ai_time=0)
            ingest_to_db(final_extraction, url, existing_craft=target_craft)
            
            # Ensure it is removed from the queue
            session = get_session()
            craft = session.query(Craft).get(target_craft.id)
            if craft and craft.status == 'In Database Queue':
                craft.status = 'Processed'
                session.commit()
            session.close()
            update_crawler_state(craft_name=query, status="Completed", progress=100)
        else:
            print("[-] AI Extraction Failed for all parts.")
            session = get_session()
            craft = session.query(Craft).get(target_craft.id)
            if craft:
                craft.status = 'AI Extraction Failed'
                session.commit()
            session.close()
            update_crawler_state(craft_name=query, status="AI Extraction Failed", progress=0)

if __name__ == "__main__":
    main()
