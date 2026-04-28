import os
import datetime
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from typing import Optional, List
from openai import OpenAI
from googlesearch import search as google_search

# Import our DB models
from app.database import get_session, engine
from app.models import Craft, Specification, Engine, Source, Media, Milestone, Base

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
        return text[:20000]  # Increased limit for data-rich pages
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
    try:
        completion = client.chat.completions.create(
            model="llama3.2",
            messages=[
                {"role": "system", "content": "You are a perfect JSON generator. Never output schemas, only output concrete data formatted perfectly to the JSON template. Do not include any text outside the JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return CraftExtraction.model_validate_json(completion.choices[0].message.content)
    except Exception as e:
        print(f"[-] AI Extraction failed: {e}")
        return None

def ingest_to_db(extraction: CraftExtraction, url: str, existing_craft: Craft):
    session = get_session()
    # We must merge it into the current session to update it
    craft = session.merge(existing_craft)

    # Force the name so the script guarantees it ties back correctly
    craft_name = extraction.name or existing_craft.name
    print(f"[+] UPDATING: Populating seeded craft '{craft_name}' with new AI extraction...")
    
    # Update base fields
    craft.alternative_names = extraction.alternative_names
    craft.designer = extraction.designer
    craft.manufacturer = extraction.manufacturer
    craft.country_of_origin = extraction.country_of_origin
    craft.year_introduced = extraction.year_introduced
    craft.operational_era = extraction.operational_era
    craft.status = extraction.status
    craft.craft_type = extraction.craft_type
    craft.description_history = extraction.description_history
    craft.operational_history = extraction.operational_history
    craft.known_accidents = extraction.known_accidents
    craft.current_location = extraction.current_location
    craft.data_confidence_score = extraction.data_confidence_score
    
    if extraction.specifications:
        craft.specifications = Specification(
            length_m=extraction.specifications.length_m,
            beam_m=extraction.specifications.beam_m,
            wingspan_m=extraction.specifications.wingspan_m,
            height_m=extraction.specifications.height_m,
            empty_weight_kg=extraction.specifications.empty_weight_kg,
            max_takeoff_weight_kg=extraction.specifications.max_takeoff_weight_kg,
            payload_capacity_kg=extraction.specifications.payload_capacity_kg,
            max_speed_kmh=extraction.specifications.max_speed_kmh,
            cruise_speed_kmh=extraction.specifications.cruise_speed_kmh,
            range_km=extraction.specifications.range_km,
            ground_effect_altitude_m=extraction.specifications.ground_effect_altitude_m,
            service_ceiling_m=extraction.specifications.service_ceiling_m,
            wing_configuration=extraction.specifications.wing_configuration,
            hull_material=extraction.specifications.hull_material,
            crew_capacity=extraction.specifications.crew_capacity,
            passenger_capacity=extraction.specifications.passenger_capacity
        )
        
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

def main():
    print("\n============= GROUND EFFECT CRAFT AI CRAWLER =============")
    client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
    
    session = get_session()
    # Find the next 5 crafts that are still in the queue (no specs populated)
    pending_crafts = session.query(Craft).filter(Craft.status == 'In Database Queue').limit(5).all()
    session.close()
    
    if not pending_crafts:
        print("No pending crafts in queue. Run seed script first.")
        return
        
    for target_craft in pending_crafts:
        # Strictly use base name to rely natively on Wiki's title match algorithm
        base_name = target_craft.name.split(" (")[0]
        query = base_name
        print(f"\n>>>> PROCESSING PENDING TARGET: {query}")
        results = perform_search(query, max_results=1)
        if not results:
            continue
            
        url = results[0].get('href')
        text = scrape_url_text(url)
        if len(text) < 200:
            print("[-] Scraped text was too short...")
            continue
            
        extraction = extract_craft_data(text, client, target_craft.name)
        if extraction:
            ingest_to_db(extraction, url, existing_craft=target_craft)
        
    print("\n============= CRAWL COMPLETE =============")

if __name__ == "__main__":
    main()
