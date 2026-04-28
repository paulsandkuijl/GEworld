from app.database import SessionLocal, engine
from app.models import Base, Craft, Specification, Engine, Source, Media, Milestone
from datetime import datetime

print("Dropping existing tables...")
Base.metadata.drop_all(bind=engine)
print("Recreating tables with new schema...")
Base.metadata.create_all(bind=engine)

session = SessionLocal()

## 1. Caspian Sea Monster (KM)
km = Craft(
    name="Caspian Sea Monster",
    alternative_names="Korabl Maket, KM",
    country_of_origin="Soviet Union",
    designer="Rostislav Alekseyev",
    manufacturer="Central Hydrofoil Design Bureau",
    status="Historical",
    craft_type="Ekranoplan",
    operational_era="1960s-1980s",
    year_introduced=1966,
    description_history="The Korabl Maket (KM), known colloquially as the Caspian Sea Monster, was an experimental ekranoplan developed by the Soviet Union in the 1960s. It was the largest and heaviest aircraft in the world until the Antonov An-225.",
    operational_history="Used exclusively for testing in the Caspian Sea. It remained a secret to the West until discovered by US spy satellites.",
    known_accidents="It crashed in 1980 due to pilot error during takeoff. It was too heavy to be recovered and sank.",
    current_location="Sunk (Caspian Sea)",
    data_confidence_score=0.95
)

# KM Specs
km_specs = Specification(
    length_m=92.0,
    wingspan_m=37.6,
    height_m=21.8,
    empty_weight_kg=240000.0,
    max_takeoff_weight_kg=544000.0,
    max_speed_kmh=500.0,
    cruise_speed_kmh=430.0,
    range_km=1500.0,
    ground_effect_altitude_m=4.0, # Flew 4 to 14 meters
    wing_configuration="Square, heavily dihedral",
    crew_capacity=5
)
km.specifications = km_specs

# KM Engines (10 turbojets total!)
km.engines.append(Engine(
    engine_name="Dobrynin VD-7",
    engine_type="Turbojet",
    quantity=10,
    thrust_kn=127.53
))

# KM Media
km.media.append(Media(
    media_type="Image",
    url="https://upload.wikimedia.org/wikipedia/commons/e/ec/Caspian_Sea_Monster.jpg",
    attribution="US DoD",
    license_type="Public Domain",
    is_primary=True
))


## 2. Boeing Pelican (ULTRA)
pelican = Craft(
    name="Boeing Pelican",
    alternative_names="Pelican ULTRA",
    country_of_origin="United States",
    designer="Boeing Phantom Works",
    manufacturer="Boeing",
    status="Concept",
    craft_type="WIG",
    operational_era="2000s",
    description_history="The Boeing Pelican ULTRA (Ultra Large Transport Aircraft) was a proposed ground effect military transport aircraft. Capable of transoceanic flight at 20 ft above water.",
    data_confidence_score=0.90
)

# Pelican Specs
pelican_specs = Specification(
    length_m=122.0,
    wingspan_m=152.0,
    max_takeoff_weight_kg=2700000.0,
    payload_capacity_kg=1270000.0,
    cruise_speed_kmh=444.0, # Over water
    range_km=18000.0,
    service_ceiling_m=6100.0, # Capable of high altitude flight at efficiency loss
    wing_configuration="Swept Wing with drooping tips"
)
pelican.specifications = pelican_specs

# Pelican Timeline
pelican.milestones.append(Milestone(year=2002, event_title="Public Reveal", event_description="Boeing publicly announced the concept study."))
pelican.milestones.append(Milestone(year=2003, event_title="Suspension", event_description="Program suspended in favor of more traditional airlift assets."))

session.add_all([km, pelican])
session.commit()
print("Successfully populated priority list!")
session.close()
