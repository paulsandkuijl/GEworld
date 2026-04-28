from app.database import SessionLocal
from app.models import Craft
from crawler import extract_craft_data, scrape_url_text, ingest_to_db
from openai import OpenAI

session = SessionLocal()
spasatel = session.query(Craft).filter(Craft.name.ilike('%Spasatel%')).first()
if not spasatel:
    print("Spasatel not found in queue.")
else:
    print(f"Targeting existing DB item: {spasatel.name}")
    url = "https://en.wikipedia.org/wiki/Spasatel"
    text = scrape_url_text(url)
    if text:
        client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
        print("Extracting via LLM...")
        extraction = extract_craft_data(text, client, spasatel.name)
        if extraction:
            print("Extraction succeeded. Updating DB...")
            ingest_to_db(extraction, url, spasatel)
            print("Done!")
        else:
            print("LLM Extraction returned None (failed formatting).")
session.close()
