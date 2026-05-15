import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database import get_session
from app.models import Craft

session = get_session()

# Find crafts with placeholder data
bad_history = "Detailed string describing history."
crafts = session.query(Craft).filter(Craft.description_history == bad_history).all()

print(f"Found {len(crafts)} crafts with placeholder history.")

for c in crafts:
    print(f"Re-queuing: {c.name}")
    c.status = 'In Database Queue'
    c.description_history = None
    c.designer = None
    c.manufacturer = None
    # Reset specs if they look like the name (numeric name issue)
    if c.specifications and str(c.specifications.length_m) == c.name:
        c.specifications.length_m = None

session.commit()
print("Re-queued all bad crafts.")
session.close()
