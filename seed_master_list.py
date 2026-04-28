import re
from app.database import SessionLocal
from app.models import Craft

# Hardcoded list of the 60 items so we don't have to parse the file dynamically right now.
crafts = [
    "Caspian Sea Monster (KM)", "A-90 Orlyonok", "Lun-class ekranoplan", "Spasatel", 
    "Bartini Beriev VVA-14", "Volga-2", "SM-1", "SM-2", "SM-3", "SM-4", "SM-5", "SM-6", 
    "SM-8", "Ekranoplan Burevestnik", "Strizh", "Amphistar", "Ivolga EK-12", "Orion-12", 
    "Orion-14", "Orion-20", "Beriev Be-2500", "Chaika A-050", "ESKA-1", "Tungus", "Dingos", 
    "RDC Aqualines EP-15", "Aquaglide-5", "Boeing Pelican ULTRA", "DARPA Liberty Lifter", 
    "DARPA FLARE", "Collins Lippisch X-112", "Collins Lippisch X-113", "Collins Lippisch X-114", 
    "Regent Viceroy", "Regent Monarch", "Aerocon Dash-1.6 megawing", "Universal Hovercraft UH-19XRW Hoverwing", 
    "Universal Hovercraft UH-18SPW", "Flying Ship Company Uncrewed WIG", "Flarecraft L-325", "SeaEagle", 
    "Tandem Airfoil Flairboat (TAF-1) Günther Jörg", "TAF VIII (Günther Jörg)", "Hoverwing HW-20", 
    "Wigetworks Airfish-8", "Airfish-3", "Aron-7", "Aron-50", "WSH-500", "Xiangzhou-1", "CASC CYG-11", 
    "Albatross (China)", "XT-100 (China)", "Haiou 34", "Chinese PAR-WIG", "Hanno-1", "Shinkansen Aerotrain", 
    "Marine Slider", "Hoverbird", "Kairyu"
]

session = SessionLocal()

for name in crafts:
    # Use split to get base name (e.g., "A-90 Orlyonok")
    base_name = name.split(" (")[0]
    
    # Check if exists
    existing = session.query(Craft).filter(Craft.name.ilike(f"%{base_name}%")).first()
    if existing is None:
        new_craft = Craft(
            name=name,
            status="In Database Queue",
            data_confidence_score=0.0
        )
        session.add(new_craft)
        print(f"[+] Seeding placeholder for: {name}")
    else:
        print(f"[*] {name} already established in DB.")

session.commit()
session.close()
print("Seeding complete.")
