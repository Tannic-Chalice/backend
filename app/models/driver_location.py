# app/models/driver_location.py

from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class DriverLiveLocation(Base):
    __tablename__ = "driver_live_location"

    id = Column(Integer, primary_key=True)
    driver_id = Column(String(10), ForeignKey("driver.id"), unique=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float)
    heading = Column(Float)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
