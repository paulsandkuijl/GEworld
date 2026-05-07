import os
from app.database import engine, init_db, SessionLocal
from app.models import Base, Craft

RAW_LIST = """
750
751 Swan
751G Swan
902
961
µSky-1
µSky-2(A)
A-1 (Aist)
A-050 Chaika-2
A-080 Chaika-3
A-90 Orlyonok S-21
A-90 Orlyonok S-23
A-90 Orlyonok S-25
A-90 Orlyonok S-26
A.90.150
А-300-538
Aero-X
Aerobel
Aerocon Dash 1.6 Wingship
Aerovironment
Airfisch 1
Airfisch 2
Airfisch 3
AirFish 8 / AF8-001
AirFish Voyager
Akergraf V-1
Akergraf V-2
Akva
Albatros (Sweden)
Albatross-5
Alexeyev 50-ton
Amphistar
Antonov An-2E
Aqua-GL
Aquaglide 5
Aquaglide 30
Aqualet
Aqualines EP-15
Aqualines Aquas
Aron M50
Aron M80
Aron-7
AWIG-1
AWIG-750
AWIG-751
Bartini Beriev VVA-14
Bavar 2
Be-1
Be-2500 Neptun
Bensen B-8MH
Beriev Be-1
Beriev Be-2500
Boeing Pelican UTRA
Bohai Sea Monster
Borey-2
Burevestnik-24
Burnelli GX-3
C-60
CASP-200
CH-1
CH-7
Challis
Cisne Branco
Colani
Collins X-112
CYG-11
D-2
DARPA Liberty Lifter
Discovery-1
Discovery-2
Do-X
Drany
DROZD unmanned WIG
DXF-100
EF-1
EF-2
EKIP
ESKA-1
Fano
FF-1
FF-2
Finnwing
Flightship 8
Flying Fish
Flying Ship
FS-8
G-1
G-2
G-3
G-4
G-5
German Slider
Haenarae-X1
Helitub
Hoverwing HW-2VT
Hoverwing HW-20
Hoverwing 50
Hoverwing 80
Hydrowing 06
Ivolga EK-12
Ivolga EK-12P
Jabiru
Jörg I
Jörg II
Jörg III
Jörg IV
Jörg V
Jörg VI
Kaario
Kiekhaefer Mercury Aeroskimmer
KM 'Caspian Sea Monster'
Korea Ocean R&D Institute Haenarae-X1
L-325
Liberty Lifter
Lippisch X-112
Lippisch X-113
Lippisch X-114
Lippisch X-117
Lockheed
Lun-class MD-160
M-6
MAGE
Mallard
Mantaray
MBB WIG concept
Navion
Pegasus
Pelican
Pennec Navion
PLA WIG UAV drones
Raduga
Raketa-2
Ram Wing
REGENT Monarch
REGENT Squire
REGENT Viceroy 'Paladin'
RFB X-113
RFB X-114
S-1
S-2
S-3
S-4
S-5
S-6
S-8
S-90-8
S-90-200
SA-1
Sail'n Fly RC02
Sea Eagle
Sea Falcon SF-08
Sea Wolf Express
Seaflight
Seafalcon
Skimmer
SM-1
SM-2
SM-2P7
SM-3
SM-4
SM-5
SM-6
SM-8
Spasatel
Strizh
Sungwoo Engineering WIG
Swan
T-501
T-701
TAF VII-3
TAF VII-5
TAF VIII-1
TAF VIII-2
TAF VIII-3
TAF VIII-4
Taimen
Thalassos
Tianyi-1
Toivola
Transal
Typhoon
Utka
UTVA Ekranoplan
Volga-2
VVA-14
Warner
Waterfly Technologies seaglider
Weiland
Wingboat
Wingship
WSH-500
WSH-1500
Xiangzhou-1
XTW-1
XTW-2
XTW-3
XTW-4
XTW-5 'Albatross'
"""

def reset_and_seed():
    print("[*] Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("[*] Initializing fresh database...")
    init_db()
    
    # Parse list
    craft_names = [line.strip() for line in RAW_LIST.split('\n') if line.strip()]
    print(f"[*] Found {len(craft_names)} unique crafts to seed.")
    
    session = SessionLocal()
    try:
        count = 0
        for name in craft_names:
            craft = Craft(
                name=name,
                status="In Database Queue",
                data_confidence_score=0.0
            )
            session.add(craft)
            count += 1
            
        session.commit()
        print(f"[+] Successfully seeded {count} crafts into the queue!")
    except Exception as e:
        session.rollback()
        print(f"[-] Error seeding database: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    reset_and_seed()
