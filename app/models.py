from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, Enum, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Craft(Base):
    __tablename__ = 'crafts'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    alternative_names = Column(String)  # Comma separated
    
    country_of_origin = Column(String, index=True)
    designer = Column(String)
    manufacturer = Column(String)
    
    status = Column(String, index=True)  # Historical, Active, In Development, Concept, Cancelled
    craft_type = Column(String, index=True)  # WIG, Ekranoplan, PAR, Concept
    operational_era = Column(String) # e.g., "1960s-1980s"
    year_introduced = Column(Integer)
    
    # Detailed Text Fields
    description_history = Column(Text)
    operational_history = Column(Text)
    known_accidents = Column(Text)
    current_location = Column(String)
    
    # Platform internal data
    data_confidence_score = Column(Float, default=0.0) # Based on number of sources

    # Relationships
    specifications = relationship("Specification", back_populates="craft", uselist=False, cascade="all, delete-orphan")
    engines = relationship("Engine", back_populates="craft", cascade="all, delete-orphan")
    sources = relationship("Source", back_populates="craft", cascade="all, delete-orphan")
    media = relationship("Media", back_populates="craft", cascade="all, delete-orphan")
    milestones = relationship("Milestone", back_populates="craft", cascade="all, delete-orphan", order_by="Milestone.year")

    def __repr__(self):
        return f"<Craft(name='{self.name}', type='{self.craft_type}', status='{self.status}')>"


class Specification(Base):
    __tablename__ = 'specifications'

    id = Column(Integer, primary_key=True)
    craft_id = Column(Integer, ForeignKey('crafts.id'), nullable=False)
    
    # Dimensions
    length_m = Column(Float)
    beam_m = Column(Float) # New
    wingspan_m = Column(Float)
    height_m = Column(Float)
    
    # Weights
    empty_weight_kg = Column(Float)
    max_takeoff_weight_kg = Column(Float)
    payload_capacity_kg = Column(Float) # New
    
    # Performance
    max_speed_kmh = Column(Float)
    cruise_speed_kmh = Column(Float)
    range_km = Column(Float)
    ground_effect_altitude_m = Column(Float)
    service_ceiling_m = Column(Float) # New
    
    # Design specifics
    wing_configuration = Column(String) # New
    hull_material = Column(String) # New
    
    # Capacity
    crew_capacity = Column(Integer) # New (split from generic capacity)
    passenger_capacity = Column(Integer) # New

    craft = relationship("Craft", back_populates="specifications")


class Engine(Base):
    __tablename__ = 'engines'

    id = Column(Integer, primary_key=True)
    craft_id = Column(Integer, ForeignKey('crafts.id'), nullable=False)
    
    engine_name = Column(String)
    engine_type = Column(String) # Turboprop, Turbofan, Piston, Electric, etc.
    quantity = Column(Integer, default=1)
    thrust_kn = Column(Float)
    power_kw = Column(Float)

    craft = relationship("Craft", back_populates="engines")


class Source(Base):
    """Citations for data points to enforce strict data quality rules."""
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    craft_id = Column(Integer, ForeignKey('crafts.id'), nullable=False)
    
    url = Column(String, nullable=False)
    title = Column(String)
    source_type = Column(String) # Primary, News, Forum, Patent, etc.
    scrape_date = Column(DateTime, default=datetime.utcnow)

    craft = relationship("Craft", back_populates="sources")


class Media(Base):
    """Stores Images, Embedded Videos, and Documents."""
    __tablename__ = 'media'
    
    id = Column(Integer, primary_key=True)
    craft_id = Column(Integer, ForeignKey('crafts.id'), nullable=False)
    
    media_type = Column(String)  # Image, Video, Document
    url = Column(String, nullable=False)
    thumbnail_url = Column(String)
    
    attribution = Column(String)
    license_type = Column(String) # CC-BY, Public Domain, Fair Use, etc.
    
    description = Column(String)
    is_primary = Column(Boolean, default=False) # E.g., main image for the Craft card

    craft = relationship("Craft", back_populates="media")


class Milestone(Base):
    """Chronological timeline events for a craft's development."""
    __tablename__ = 'milestones'
    
    id = Column(Integer, primary_key=True)
    craft_id = Column(Integer, ForeignKey('crafts.id'), nullable=False)
    
    year = Column(Integer, nullable=False)
    month = Column(Integer)  # Optional
    event_title = Column(String, nullable=False)
    event_description = Column(Text)

    craft = relationship("Craft", back_populates="milestones")
