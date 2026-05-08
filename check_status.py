import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database import get_session
from app.models import Craft

session = get_session()
crafts = session.query(Craft).filter(Craft.name.like('%Lun%') | Craft.name.like('%MD-160%')).all()
if not crafts:
    print("No Lun or MD-160 found.")
for c in crafts:
    print(f"{c.id}: {c.name} - {c.status}")
session.close()
