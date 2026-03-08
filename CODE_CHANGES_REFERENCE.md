# Code Changes - Complete File Reference

## Overview
This document shows all the files that were created or modified for the daily random variation analytics implementation.

## New Files Created

### 1. Service Layer
**File**: `app/services/daily_analytics_service.py` (NEW - 347 lines)

**Purpose**: Core service for generating daily analytics with random variations

**Key Classes/Functions**:
- `DailyAnalyticsGenerator`: Main generator class
  - `generate_random_variation()`: Returns random value between -0.25 and 0.25
  - `calculate_quantity_with_variation()`: Applies variation to base quantity
  - `generate_daily_analytics_for_bwg()`: Creates analytics for specific BWG
  - `generate_daily_analytics_for_vehicle()`: Creates analytics for specific vehicle
  - `generate_total_processing_analytics()`: Creates total processing analytics
  - `regenerate_daily_analytics()`: Batch generates for all entities
- `get_daily_analytics_generator()`: Factory function

**Imports**:
```python
from app.models import DailyProcessingAnalytics, Bwg, Vehicle, Pickup, Trip
```

---

### 2. Scheduler Configuration
**File**: `app/scheduler.py` (NEW - 73 lines)

**Purpose**: Background scheduler using APScheduler

**Key Functions**:
- `init_scheduler()`: Initializes APScheduler with daily cron job
  - Runs at 00:05 UTC daily
  - Calls `DailyAnalyticsGenerator.regenerate_daily_analytics()`
  - Max 1 instance to prevent duplicates
- `shutdown_scheduler()`: Gracefully shuts down scheduler
- `trigger_daily_analytics()`: Manual trigger for analytics generation

**Configuration**:
```python
scheduler.add_job(
    func=DailyAnalyticsGenerator.regenerate_daily_analytics,
    trigger=CronTrigger(hour=0, minute=5),  # Change this
    id='daily_analytics_generation',
    name='Daily Analytics Generation',
    replace_existing=True,
    max_instances=1
)
```

---

### 3. Database Migration
**File**: `migrations/add_daily_processing_analytics.sql` (NEW - 30 lines)

**Purpose**: Creates the daily_processing_analytics table

**Schema**:
```sql
CREATE TABLE daily_processing_analytics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    bwg_id VARCHAR(10) REFERENCES bwg(id) ON DELETE CASCADE,
    vehicle_id INTEGER REFERENCES vehicles(vehicle_id) ON DELETE CASCADE,
    
    bwg_wise_variation_percent NUMERIC(5, 1),
    vehicle_wise_variation_percent NUMERIC(5, 1),
    total_processing_variation_percent NUMERIC(5, 1),
    
    bwg_wise_quantity_kg NUMERIC(12, 2),
    vehicle_wise_quantity_kg NUMERIC(12, 2),
    total_processing_quantity_kg NUMERIC(12, 2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(date, bwg_id, vehicle_id)
);

-- Indices for performance
CREATE INDEX idx_daily_analytics_date
CREATE INDEX idx_daily_analytics_bwg_id
CREATE INDEX idx_daily_analytics_vehicle_id
CREATE INDEX idx_daily_analytics_date_bwg
CREATE INDEX idx_daily_analytics_date_vehicle
```

---

### 4. Documentation Files
**Files**:
- `DAILY_ANALYTICS_IMPLEMENTATION.md` (Comprehensive implementation guide)
- `DAILY_ANALYTICS_QUICK_REF.md` (Quick reference guide)
- `DAILY_ANALYTICS_SUMMARY.md` (Executive summary)

---

## Modified Files

### 1. Models
**File**: `app/models.py`

**Change**: Added new SQLAlchemy model after `BwgDailyAggregate` class

**Code Added** (Lines 225-256):
```python
class DailyProcessingAnalytics(Base):
    """
    Daily processing analytics with random variations within ±25% range.
    Stores three types of data:
    - BWG Wise: Variation for specific BWGs on given date
    - Vehicle Wise: Variation for specific vehicles on given date
    - Total Processing: Variation for total daily processing
    """
    __tablename__ = "daily_processing_analytics"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    bwg_id = Column(String(10), ForeignKey("bwg.id", ondelete="CASCADE"), index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="CASCADE"), nullable=True, index=True)
    
    bwg_wise_variation_percent = Column(Numeric(5, 1), nullable=True)
    vehicle_wise_variation_percent = Column(Numeric(5, 1), nullable=True)
    total_processing_variation_percent = Column(Numeric(5, 1), nullable=True)
    
    bwg_wise_quantity_kg = Column(Numeric(12, 2), nullable=True)
    vehicle_wise_quantity_kg = Column(Numeric(12, 2), nullable=True)
    total_processing_quantity_kg = Column(Numeric(12, 2), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    bwg = relationship("Bwg", foreign_keys=[bwg_id])
```

**Location**: Between `BwgDailyAggregate` and `BillingContract` classes

---

### 2. Main Application File
**File**: `app/main.py`

**Change 1** (Line 25): Added import
```python
from app.scheduler import init_scheduler, shutdown_scheduler
```

**Change 2** (Lines 94-108): Added startup and shutdown events
```python
@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on application startup."""
    try:
        init_scheduler()
        logger.info("Application startup complete - scheduler initialized")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler on startup: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown scheduler on application shutdown."""
    try:
        shutdown_scheduler()
        logger.info("Application shutdown complete - scheduler stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
```

---

### 3. Reports Router
**File**: `app/routers/admin/reports.py`

**Change 1** (Line 1-8): Updated imports
```python
from fastapi import APIRouter, HTTPException
from app.database import get_db
from psycopg2.extras import RealDictCursor
from app.services.waste_calculator import get_waste_calculator
from app.services.daily_analytics_service import DailyAnalyticsGenerator  # NEW
from datetime import date
import logging
import calendar
import random
```

**Change 2** (Lines 348-506): Added 4 new API endpoints at end of file

#### Endpoint 1: GET /admin/daily-analytics/bwg-wise/{bwg_id}
```python
@router.get("/daily-analytics/bwg-wise/{bwg_id}")
def get_bwg_wise_daily_analytics(bwg_id: str, from_date: str = None, to_date: str = None):
    # Returns analytics for specific BWG with variation % and calculated quantities
```

#### Endpoint 2: GET /admin/daily-analytics/vehicle-wise/{vehicle_id}
```python
@router.get("/daily-analytics/vehicle-wise/{vehicle_id}")
def get_vehicle_wise_daily_analytics(vehicle_id: int, from_date: str = None, to_date: str = None):
    # Returns analytics for specific vehicle with variation % and calculated quantities
```

#### Endpoint 3: GET /admin/daily-analytics/total-processing
```python
@router.get("/daily-analytics/total-processing")
def get_total_processing_daily_analytics(from_date: str = None, to_date: str = None):
    # Returns total daily processing analytics with variation % and calculated quantities
```

#### Endpoint 4: POST /admin/daily-analytics/regenerate
```python
@router.post("/daily-analytics/regenerate")
def regenerate_daily_analytics(target_date: str = None):
    # Manually triggers analytics regeneration for specific date or today
```

---

### 4. Requirements Files
**Files**: `requirements.txt` and `req.txt`

**Change**: Added dependency after `anyio==4.12.0`
```
apscheduler==3.10.4
```

**Location**: Line 4 in both files (alphabetically sorted)

---

## Summary of Changes

### Code Statistics
| Component | Type | Lines | Status |
|-----------|------|-------|--------|
| daily_analytics_service.py | NEW | 347 | ✅ Created |
| scheduler.py | NEW | 73 | ✅ Created |
| add_daily_processing_analytics.sql | NEW | 30 | ✅ Created |
| models.py | MODIFIED | +32 | ✅ Updated |
| main.py | MODIFIED | +3 import, +17 code | ✅ Updated |
| reports.py | MODIFIED | +4 imports, +159 code | ✅ Updated |
| requirements.txt | MODIFIED | +1 dependency | ✅ Updated |
| req.txt | MODIFIED | +1 dependency | ✅ Updated |

**Total New Code**: ~450 lines
**Total Modified**: ~50 lines
**Total Files**: 8 (3 new, 5 modified)

---

## Dependency Tree

```
app/main.py
├── app/scheduler.py
│   └── app/services/daily_analytics_service.py
│       ├── app/models.py (DailyProcessingAnalytics)
│       ├── app/database.py
│       └── External: sqlalchemy, logging
│
└── app/routers/admin/reports.py
    ├── app/services/daily_analytics_service.py
    ├── app/database.py
    └── External: fastapi, psycopg2
```

---

## Database Changes

### New Table
```
daily_processing_analytics
- Stores daily variations for BWGs, vehicles, and total processing
- Unique constraint: (date, bwg_id, vehicle_id)
- Indices on: date, bwg_id, vehicle_id, and combinations
```

### Relationships
```
daily_processing_analytics.bwg_id FK→ bwg.id
daily_processing_analytics.vehicle_id FK→ vehicles.vehicle_id
```

---

## Environment Requirements

### New Python Package
```
apscheduler==3.10.4
```

### Existing Packages Used
- sqlalchemy (models)
- fastapi (routing)
- psycopg2 (database)
- pytz (timezone handling)

---

## Configuration Points

### 1. Scheduler Time
**File**: `app/scheduler.py` (Line ~31)
```python
trigger=CronTrigger(hour=0, minute=5)
```

### 2. Variation Range
**File**: `app/services/daily_analytics_service.py` (Lines ~27-28)
```python
VARIATION_MIN = -0.25
VARIATION_MAX = 0.25
```

### 3. Database Connection
**Uses**: Existing `get_db()` from `app/database.py`

---

## Testing Checklist

- [ ] APScheduler installed (`pip list | grep apscheduler`)
- [ ] Database migration run (`psql ... -f migrations/add_daily_processing_analytics.sql`)
- [ ] App starts without errors
- [ ] Scheduler initializes (check startup logs)
- [ ] Manual regeneration works (`POST /admin/daily-analytics/regenerate`)
- [ ] Endpoints return data (`GET /admin/daily-analytics/total-processing`)
- [ ] Data persists in database
- [ ] No errors in application logs

---

## Version Control

All files are ready for git commit:
```bash
git add app/models.py
git add app/main.py
git add app/scheduler.py
git add app/services/daily_analytics_service.py
git add app/routers/admin/reports.py
git add requirements.txt
git add req.txt
git add migrations/add_daily_processing_analytics.sql
git add DAILY_ANALYTICS_*.md

git commit -m "feat: Add daily random variation analytics for admin dashboard

- Adds DailyProcessingAnalytics model for storing daily variations
- Implements DailyAnalyticsGenerator service with ±25% random variations
- Adds APScheduler for daily 00:05 UTC regeneration
- Adds 4 REST API endpoints for fetching analytics
- Includes database migration for new table with indices
- Fully documented with implementation and quick reference guides"
```

---

## Rollback Plan (If Needed)

### To Revert Changes:
1. **Revert code**:
   ```bash
   git revert <commit-hash>
   ```

2. **Drop database table** (optional):
   ```sql
   DROP TABLE daily_processing_analytics;
   ```

3. **Reinstall without apscheduler**:
   ```bash
   pip install -r requirements.txt
   ```

### What Will Be Lost:
- All historical analytics data in `daily_processing_analytics` table
- Functionality for daily variation analytics

---

## Maintenance Notes

### Regular Monitoring
- Check scheduler logs daily for successful regeneration
- Verify data in table: `SELECT COUNT(*) FROM daily_processing_analytics;`
- Monitor for any exceptions in application logs

### Optional Enhancements
- Add caching for frequently queried date ranges
- Add data retention policy (e.g., keep 1 year of data)
- Add metrics/monitoring for scheduler execution time

---

## Contact & Support

For questions about this implementation, refer to:
1. `DAILY_ANALYTICS_IMPLEMENTATION.md` - Comprehensive docs
2. `DAILY_ANALYTICS_QUICK_REF.md` - Quick reference
3. Code comments in `daily_analytics_service.py`
4. API documentation in `reports.py`
