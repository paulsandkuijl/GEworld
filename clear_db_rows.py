from app.database import SessionLocal
from app.models import Craft

session = SessionLocal()
session.query(Craft).delete()
session.commit()
session.close()
print("All crafts deleted.")
