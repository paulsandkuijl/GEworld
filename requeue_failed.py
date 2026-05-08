from app.database import get_session
from app.models import Craft

session = get_session()
# Reset Lun and any failed crafts
crafts = session.query(Craft).filter(Craft.status.in_(['Unknown', 'AI Extraction Failed', 'No Results Found', 'Insufficient Text'])).all()
print(f"Re-queuing {len(crafts)} crafts...")
for c in crafts:
    c.status = 'In Database Queue'
session.commit()
session.close()
