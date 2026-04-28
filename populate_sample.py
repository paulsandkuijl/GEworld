import datetime
from database import init_db, get_session
from models import Craft, Specification, Engine, Source

def populate_regent_viceroy():
    init_db()
    
    session = get_session()
    
    # Check if exists to avoid duplication entirely
    existing_craft = session.query(Craft).filter_by(name="Viceroy (Seaglider)").first()
    if existing_craft:
        print("Viceroy craft already exists in the database. Deleting to recreate sample...")
        session.delete(existing_craft)
        session.commit()

    # Create the Craft Entry
    viceroy = Craft(
        name="Viceroy (Seaglider)",
        designer="REGENT Craft",
        country_of_origin="United States",
        year_introduced=2025, # Expected timeframe
        status="In Development",
        description_history="The Viceroy is a 12-passenger, all-electric wing-in-ground-effect craft (called a Seaglider by REGENT). It operates in three modes: hull, hydrofoil, and flight in ground effect over water."
    )
    
    # Create matching technical specifications
    viceroy.specifications = Specification(
        cruise_speed_kmh=290, # up to 180 mph = ~290 km/h
        range_km=290, # 180 miles with current battery tech = ~290 km
        capacity="12 passengers or 3,500 lbs cargo"
    )
    
    # Add Engine/Propulsion Details
    engine = Engine(
        engine_type="Electric Motors",
        quantity=8,
    )
    viceroy.engines.append(engine)
    
    # Add where this test data came from
    source = Source(
        url="https://www.regentcraft.com/seagliders/viceroy",
        scrape_date=datetime.datetime.now()
    )
    viceroy.sources.append(source)
    
    # Add to DB and Commit
    session.add(viceroy)
    session.commit()
    
    print("\n--- Inserted Sample Data ---")
    print(f"Craft inserted: {viceroy}")
    
    # Verify retrieval
    retrieved = session.query(Craft).first()
    print("\n--- Retrieving Sample Data ---")
    print(f"Name: {retrieved.name}")
    print(f"Manufacturer: {retrieved.designer}")
    print(f"Speed: {retrieved.specifications.cruise_speed_kmh} km/h")
    print(f"Engines: {len(retrieved.engines)}x {retrieved.engines[0].engine_type}")
    print(f"Source URL: {retrieved.sources[0].url}")
    
    session.close()

if __name__ == "__main__":
    populate_regent_viceroy()
