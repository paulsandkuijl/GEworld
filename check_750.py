import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database import get_session
from app.models import Craft

session = get_session()
craft = session.query(Craft).filter(Craft.name == '750').first()

if craft:
    print(f"Name: {craft.name}")
    print(f"Status: {craft.status}")
    print(f"Designer: {craft.designer}")
    print(f"History: {craft.description_history}")
    print(f"Specs: {craft.specifications.length_m if craft.specifications else 'None'}")
else:
    print("Craft '750' not found.")

session.close()
