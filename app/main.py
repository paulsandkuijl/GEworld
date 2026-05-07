from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel as PyBaseModel
import json
import os
import datetime

from app.database import get_db, get_session, init_db
from app.models import Craft, Specification, Engine, Source

app = FastAPI(title="Ground Effect World API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/crafts")
def list_crafts(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    search: Optional[str] = None
):
    query = db.query(Craft)
    if search:
        query = query.filter(Craft.name.ilike(f"%{search}%"))
    crafts = query.offset(skip).limit(limit).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "country_of_origin": c.country_of_origin,
            "year_introduced": c.year_introduced,
            "designer": c.designer,
            "media": [{"url": c.media[0].url}] if c.media else []
        } for c in crafts
    ]

@app.get("/api/crafts/{craft_id}")
def get_craft(craft_id: int, db: Session = Depends(get_db)):
    craft = db.query(Craft).filter(Craft.id == craft_id).first()
    if not craft:
        raise HTTPException(status_code=404, detail="Craft not found")
    spec = craft.specifications
    return {
        "id": craft.id,
        "name": craft.name,
        "alternative_names": craft.alternative_names,
        "country_of_origin": craft.country_of_origin,
        "designer": craft.designer,
        "manufacturer": craft.manufacturer,
        "craft_type": craft.craft_type,
        "operational_era": craft.operational_era,
        "year_introduced": craft.year_introduced,
        "status": craft.status,
        "description_history": craft.description_history,
        "operational_history": craft.operational_history,
        "known_accidents": craft.known_accidents,
        "current_location": craft.current_location,
        "data_confidence_score": craft.data_confidence_score,
        "specifications": {
            "length_m": spec.length_m if spec else None,
            "beam_m": spec.beam_m if spec else None,
            "wingspan_m": spec.wingspan_m if spec else None,
            "height_m": spec.height_m if spec else None,
            "max_takeoff_weight_kg": spec.max_takeoff_weight_kg if spec else None,
            "payload_capacity_kg": spec.payload_capacity_kg if spec else None,
            "max_speed_kmh": spec.max_speed_kmh if spec else None,
            "cruise_speed_kmh": spec.cruise_speed_kmh if spec else None,
            "range_km": spec.range_km if spec else None,
            "ground_effect_altitude_m": spec.ground_effect_altitude_m if spec else None,
            "wing_configuration": spec.wing_configuration if spec else None,
        } if spec else None,
        "engines": [
            {"engine_name": e.engine_name, "type": e.engine_type, "quantity": e.quantity}
            for e in craft.engines
        ],
        "media": [
            {"type": m.media_type, "url": m.url, "attribution": m.attribution, "is_primary": m.is_primary}
            for m in craft.media
        ],
        "milestones": [
            {"year": m.year, "title": m.event_title, "description": m.event_description}
            for m in craft.milestones
        ]
    }


# ── Craft Update ─────────────────────────────────────────────────────────────

class CraftUpdateModel(PyBaseModel):
    name: Optional[str] = None
    alternative_names: Optional[str] = None
    country_of_origin: Optional[str] = None
    designer: Optional[str] = None
    manufacturer: Optional[str] = None
    craft_type: Optional[str] = None
    operational_era: Optional[str] = None
    year_introduced: Optional[int] = None
    status: Optional[str] = None
    description_history: Optional[str] = None
    operational_history: Optional[str] = None
    known_accidents: Optional[str] = None
    current_location: Optional[str] = None
    # Specification fields
    length_m: Optional[float] = None
    beam_m: Optional[float] = None
    wingspan_m: Optional[float] = None
    height_m: Optional[float] = None
    max_takeoff_weight_kg: Optional[float] = None
    payload_capacity_kg: Optional[float] = None
    max_speed_kmh: Optional[float] = None
    cruise_speed_kmh: Optional[float] = None
    range_km: Optional[float] = None
    ground_effect_altitude_m: Optional[float] = None
    wing_configuration: Optional[str] = None

@app.patch("/api/crafts/{craft_id}")
def update_craft(craft_id: int, payload: CraftUpdateModel, db: Session = Depends(get_db)):
    craft = db.query(Craft).filter(Craft.id == craft_id).first()
    if not craft:
        raise HTTPException(status_code=404, detail="Craft not found")

    craft_fields = [
        'name', 'alternative_names', 'country_of_origin', 'designer', 'manufacturer',
        'craft_type', 'operational_era', 'year_introduced', 'status',
        'description_history', 'operational_history', 'known_accidents', 'current_location'
    ]
    spec_fields = [
        'length_m', 'beam_m', 'wingspan_m', 'height_m', 'max_takeoff_weight_kg',
        'payload_capacity_kg', 'max_speed_kmh', 'cruise_speed_kmh', 'range_km',
        'ground_effect_altitude_m', 'wing_configuration'
    ]

    update_data = payload.model_dump(exclude_unset=True)

    for field in craft_fields:
        if field in update_data:
            setattr(craft, field, update_data[field])

    spec_updates = {f: update_data[f] for f in spec_fields if f in update_data}
    if spec_updates:
        if craft.specifications:
            for field, value in spec_updates.items():
                setattr(craft.specifications, field, value)
        else:
            from app.models import Specification
            spec = Specification(craft_id=craft_id, **spec_updates)
            db.add(spec)

    db.commit()
    db.refresh(craft)
    return {"success": True, "id": craft.id}


# ── Manual URL Ingestion (SSE Streaming) ──────────────────────────────────────

class CrawlRequest(PyBaseModel):
    url: Optional[str] = None
    craft_name: Optional[str] = None

@app.post("/api/crawl-url")
async def crawl_url(payload: CrawlRequest):
    """
    SSE streaming crawl endpoint. Yields a JSON progress line per stage:
    search -> scrape -> LLM extract -> DB save -> done
    """
    if not payload.url and not payload.craft_name:
        raise HTTPException(status_code=400, detail="Provide a craft name, a URL, or both.")

    def sse(msg: str, etype: str = "progress", **kwargs) -> str:
        data = {"type": etype, "message": msg}
        data.update(kwargs)
        return "data: " + json.dumps(data) + "\n\n"

    def stream():
        from openai import OpenAI
        from crawler import scrape_url_text, extract_craft_data, ingest_to_db, perform_search
        from app.database import SessionLocal
        from app.models import Craft

        db = SessionLocal()
        try:
            craft_name_hint = payload.craft_name or "Unknown Ground Effect Craft"

            # Stage 1 – resolve URL(s)
            if payload.url:
                url = payload.url.strip()
                if not url.startswith("http"):
                    yield sse("Invalid URL — must start with http:// or https://", etype="error")
                    return
                urls_to_try = [url]
                search_mode = False
                yield sse("Using provided URL: " + url)
            else:
                search_mode = True
                yield sse("Searching Wikipedia for \"" + craft_name_hint + "\"...")
                wiki_results = perform_search(craft_name_hint, max_results=3)
                urls_to_try = [r["href"] for r in wiki_results]
                if not urls_to_try:
                    yield sse("No Wikipedia pages found for \"" + craft_name_hint + "\". Try adding a URL manually.", etype="error")
                    return
                yield sse("Found " + str(len(urls_to_try)) + " candidate page(s) on Wikipedia.")

            # Stage 2 – scrape
            text = ""
            final_url = None
            for candidate_url in urls_to_try:
                short = candidate_url.replace("https://en.wikipedia.org/wiki/", "wikipedia: ")
                yield sse("Scraping " + short + "...")
                scraped = scrape_url_text(candidate_url)
                if len(scraped) >= 300:
                    text = scraped
                    final_url = candidate_url
                    yield sse("Extracted " + str(len(text)) + " characters of clean content.")
                    break
                else:
                    yield sse("Too little content (" + str(len(scraped)) + " chars), trying next...")

            if not text:
                msg = ("Found pages but none had enough content. Try a direct URL."
                       if search_mode else "Could not extract enough content from that URL.")
                yield sse(msg, etype="error")
                return

            # Stage 3 – LLM extraction
            yield sse("Sending content to Ollama AI for extraction...")
            yield sse("AI is reading and structuring craft data (this takes ~1 min)...")
            client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            extraction = extract_craft_data(text, client, craft_name_hint)

            if not extraction:
                yield sse("AI extraction failed. Is Ollama running?", etype="error")
                return

            yield sse("AI extraction complete for \"" + (extraction.name or craft_name_hint) + "\".")

            # Stage 4 – upsert
            yield sse("Saving to database...")
            extracted_name = extraction.name or craft_name_hint
            existing = db.query(Craft).filter(Craft.name.ilike("%" + extracted_name + "%")).first()

            if existing:
                yield sse("Updating existing entry: \"" + existing.name + "\"")
                conflicts = ingest_to_db(extraction, final_url, existing_craft=existing, reconcile=True)
                saved_id = existing.id
            else:
                yield sse("Creating new entry: \"" + extracted_name + "\"")
                new_craft = Craft(name=extracted_name, status="In Database Queue", data_confidence_score=0.0)
                db.add(new_craft)
                db.commit()
                db.refresh(new_craft)
                conflicts = ingest_to_db(extraction, final_url, existing_craft=new_craft, reconcile=False)
                saved_id = new_craft.id

            if conflicts:
                yield sse(
                    "Reconciliation required for " + str(len(conflicts)) + " fields.",
                    etype="conflict_resolution",
                    craft_id=saved_id,
                    craft_name=extracted_name,
                    conflicts=conflicts
                )
            else:
                yield sse(
                    "Saved: \"" + extracted_name + "\"",
                    etype="done",
                    craft_id=saved_id,
                    craft_name=extracted_name,
                    source_url=final_url,
                    auto_searched=search_mode
                )

        except Exception as e:
            yield sse("Unexpected error: " + str(e), etype="error")
        finally:
            db.close()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ── Admin / Crawler Status ────────────────────────────────────────────────────

STATE_FILE = "crawler_state.json"

@app.get("/api/crawler/status")
def get_crawler_status():
    """Read the crawler state file written by the background crawler process."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            # Flag as stale if not updated in the last 5 minutes
            last_updated = state.get("last_updated")
            if last_updated:
                age = (datetime.datetime.now() - datetime.datetime.fromisoformat(last_updated)).total_seconds()
                state["is_stale"] = age > 180  # 120s Ollama timeout + 60s buffer
            return state
    except Exception:
        pass
    return {
        "current_craft": None,
        "status": "Offline",
        "progress": 0,
        "queue_remaining": 0,
        "total_processed": 0,
        "last_updated": None,
        "is_stale": True
    }

@app.get("/admin")
def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")
