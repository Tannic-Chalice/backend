#!/usr/bin/env python
"""Test script to manually trigger and debug daily tasks"""

from app.database import SessionLocal
from app.models import Bwg, Vehicle, Supervisor
from app.services.daily_analytics_service import DailyAnalyticsGenerator, BwgCollectionReportGenerator
from datetime import date
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("Testing model queries...")
db = SessionLocal()
try:
    # Test BWG query
    bwgs = db.query(Bwg).filter(Bwg.status == 'approved').all()
    print(f"✓ Found {len(bwgs)} approved BWGs")
    
    # Test vehicle query
    vehicles = db.query(Vehicle).all()
    print(f"✓ Found {len(vehicles)} vehicles")
    
    # Test supervisor query
    supervisors = db.query(Supervisor).all()
    print(f"✓ Found {len(supervisors)} supervisors")
    
    print("\nTesting analytics generation...")
    stats = DailyAnalyticsGenerator.regenerate_daily_analytics(date.today())
    print(f"✓ Analytics: {stats}")
    
    print("\nTesting BWG collection reports...")
    bwg_stats = BwgCollectionReportGenerator.generate_collection_reports_for_date(date.today())
    print(f"✓ BWG Reports: {bwg_stats}")
    
    print("\n✅ ALL TESTS PASSED - Ready to deploy")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
