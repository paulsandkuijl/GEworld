import os
import datetime
import requests
import json
import time
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

def update_crawler_state(craft_name="None", status="Idle", progress=0):
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
def perform_search(query: str, max_results: int = 2) -> list[dict]:
    print(f"[*] Searching Wikipedia for: '{query}'")
    try:
        headers = {'User-Agent': 'GroundEffectCrawler/2.0'}
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": "",
            "format": "json"
        }
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        urls = []
        for item in data.get('query', {}).get('search', [])[:max_results]:
            title_formatted = item['title'].replace(' ', '_')
            urls.append({'href': f"https://en.wikipedia.org/wiki/{title_formatted}"})
            
        return urls
    except Exception as e:
        print(f"[-] Search failed: {e}")
        return []

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

        # Also remove common ad/cookie/comment class names
        for cls in ["cookie", "banner", "advertisement", "popup", "sidebar", "comment", "share", "social", "promo"]:
            for el in soup.find_all(class_=lambda c: c and cls in c.lower()):
                el.decompose()

        # Prefer the main article content if it exists
        main_content = soup.find('article') or soup.find('main') or soup.find(id='content') or soup.find(id='bodyContent') or soup.body
        
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)

        # Collapse excessive whitespace
        import re
        text = re.sub(r'\s{2,}', ' ', text)
        
        print(f"[*] Scraped {len(text)} characters of clean text.")
        return text[:7500]  # llama3.2 has ~8192 token context; 7500 chars leaves headroom for the prompt
    except Exception as e:
        print(f"[-] Failed to scrape {url}: {e}")
        return ""

def extract_craft_data(text: str, client: OpenAI, craft_name: str) -> Optional[CraftExtraction]:
    print(f"[*] Sending text for '{craft_name}' to local Ollama inference engine for extraction...")
    prompt = f"""
    You are a technical data extractor processing the Wing-in-Ground (WIG) craft named "{craft_name}".
    ASSUME it is a valid winged GEC. 
    Extract the specifications, operational history, engines, milestones, and media from the TEXT below.
    You MUST output valid, parsable JSON matching this EXACT template. Replace nulls with data if found. Do NOT use $ref or schema definitions.

    {{
        "found_craft": true,
        "data_confidence_score": 1.0,
        "name": "{craft_name}",
        "alternative_names": "Unknown",
        "designer": "Unknown",
        "manufacturer": "Unknown",
        "country_of_origin": "Unknown",
        "year_introduced": 1980,
        "operational_era": "Unknown",
        "status": "Unknown",
        "craft_type": "Ekranoplan",
        "description_history": "Detailed string describing history.",
        "operational_history": "Detailed string describing operations.",
        "known_accidents": "Detailed string describing accidents.",
        "current_location": "Unknown",
        "specifications": {{
            "length_m": null,
            "beam_m": null,
            "wingspan_m": null,
            "height_m": null,
            "empty_weight_kg": null,
            "max_takeoff_weight_kg": null,
            "payload_capacity_kg": null,
            "max_speed_kmh": null,
            "cruise_speed_kmh": null,
            "range_km": null,
            "ground_effect_altitude_m": null,
            "service_ceiling_m": null,
            "wing_configuration": null,
            "hull_material": null,
            "crew_capacity": null,
            "passenger_capacity": null
        }},
        "engines": [
            {{"engine_name": "example", "engine_type": "turbofan", "quantity": 1, "thrust_kn": null, "power_kw": null}}
        ],
        "media": [
            {{"media_type": "Image", "url": "https://example.com/img.jpg", "attribution": null, "description": null}}
        ],
        "milestones": [
            {{"year": 1980, "event_title": "Example", "event_description": null}}
        ]
    }}
    
    TEXT:
    {text}
    """
    import concurrent.futures

    def _call_ollama():
        return client.chat.completions.create(
            model="llama3.2",
            messages=[
                {"role": "system", "content": "You are a perfect JSON generator. Never output schemas, only output concrete data formatted perfectly to the JSON template. Do not include any text outside the JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            timeout=90  # HTTP-level socket timeout
        )

    try:
        # Thread-based hard deadline: if Ollama doesn't respond in 90s, cancel
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_ollama)
            try:
                completion = future.result(timeout=90)
            except concurrent.futures.TimeoutError:
                print(f"[-] AI Extraction timed out after 90s for '{craft_name}' — skipping.")
                return None
        return CraftExtraction.model_validate_json(completion.choices[0].message.content)
    except Exception as e:
        print(f"[-] AI Extraction failed: {e}")
        return None

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
        
    for m in extraction.media:
        if m.url:
            craft.media.append(Media(
                media_type=m.media_type, url=m.url, attribution=m.attribution, description=m.description
            ))
            
    for ms in extraction.milestones:
        craft.milestones.append(Milestone(
            year=ms.year, event_title=ms.event_title, event_description=ms.event_description
        ))
        
    craft.sources.append(Source(url=url, source_type="Primary", scrape_date=datetime.datetime.now()))

    session.commit()
    print(f"[+] Successfully saved '{craft.name}' fully mapped to expanded schema!")
    session.close()
    return conflicts

def main():
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
            
        update_crawler_state(craft_name=query, status="Extracting via AI (Ollama)...", progress=60)
        extraction = extract_craft_data(text, client, target_craft.name)
        if extraction:
            update_crawler_state(craft_name=query, status="Saving to Database...", progress=90)
            ingest_to_db(extraction, url, existing_craft=target_craft)
            
            # Ensure it is removed from the queue
            session = get_session()
            craft = session.query(Craft).get(target_craft.id)
            if craft and craft.status == 'In Database Queue':
                craft.status = 'Processed'
                session.commit()
            session.close()
            update_crawler_state(craft_name=query, status="Completed", progress=100)
        else:
            print("[-] AI Extraction Failed.")
            session = get_session()
            craft = session.query(Craft).get(target_craft.id)
            if craft:
                craft.status = 'AI Extraction Failed'
                session.commit()
            session.close()
            update_crawler_state(craft_name=query, status="AI Extraction Failed", progress=0)

if __name__ == "__main__":
    main()
