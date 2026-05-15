import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database import get_session
from app.models import Craft
from sqlalchemy import func

session = get_session()
counts = session.query(Craft.status, func.count(Craft.id)).group_by(Craft.status).all()

print("Status Counts:")
for status, count in counts:
    print(f"{status}: {count}")

total = session.query(func.count(Craft.id)).scalar()
print(f"\nTotal Crafts: {total}")

session.close()
