# Daily Random Variation Analytics Implementation

## Overview
This implementation adds daily random variation generation (±25% range) to the admin dashboard reports for:
- **BWG Wise Processing**: Random variations for individual BWGs
- **Vehicle Wise Processing**: Random variations for individual vehicles  
- **Total Processing**: Random variations for total daily processing

## Implementation Details

### 1. Database Model
**File**: [app/models.py](app/models.py)

Added new SQLAlchemy model `DailyProcessingAnalytics` to store daily variations:

```python
class DailyProcessingAnalytics(Base):
    __tablename__ = "daily_processing_analytics"
    
    id: Primary key
    date: Date for the analytics
    bwg_id: Reference to BWG (nullable)
    vehicle_id: Reference to Vehicle (nullable)
    
    # Variation percentages (±25%)
    bwg_wise_variation_percent: NUMERIC(5, 1)
    vehicle_wise_variation_percent: NUMERIC(5, 1)
    total_processing_variation_percent: NUMERIC(5, 1)
    
    # Calculated quantities
    bwg_wise_quantity_kg: NUMERIC(12, 2)
    vehicle_wise_quantity_kg: NUMERIC(12, 2)
    total_processing_quantity_kg: NUMERIC(12, 2)
```

**Note**: When both `bwg_id` and `vehicle_id` are NULL, the record represents total processing analytics.

### 2. Service Layer
**File**: [app/services/daily_analytics_service.py](app/services/daily_analytics_service.py)

`DailyAnalyticsGenerator` class provides:

#### Methods:
- `generate_random_variation()`: Generates random variation between -25% and +25%
- `calculate_quantity_with_variation()`: Applies variation to base quantity
- `generate_daily_analytics_for_bwg()`: Creates analytics for specific BWG
- `generate_daily_analytics_for_vehicle()`: Creates analytics for specific vehicle
- `generate_total_processing_analytics()`: Creates total processing analytics
- `regenerate_daily_analytics()`: Batch regenerates all analytics for a date

#### Key Features:
- Non-uniform random variation distribution
- Daily quantity calculated as: `base_quantity × (1 + variation_percent/100)`
- Automatic daily regeneration via scheduler
- Supports backdating for historical analytics

### 3. Scheduler
**File**: [app/scheduler.py](app/scheduler.py)

Background scheduler using APScheduler:
- **Schedule**: Daily at 00:05 UTC (configurable)
- **Job**: `DailyAnalyticsGenerator.regenerate_daily_analytics()`
- **Scope**: Regenerates analytics for all approved BWGs and active vehicles

#### Configuration:
```python
# Run at 00:05 UTC daily
scheduler.add_job(
    func=DailyAnalyticsGenerator.regenerate_daily_analytics,
    trigger=CronTrigger(hour=0, minute=5),
    id='daily_analytics_generation',
    max_instances=1  # Prevent duplicate runs
)
```

**To adjust time**: Edit `hour` and `minute` parameters in [app/scheduler.py](app/scheduler.py)

### 4. API Endpoints
**File**: [app/routers/admin/reports.py](app/routers/admin/reports.py)

#### GET `/admin/daily-analytics/bwg-wise/{bwg_id}`
Get BWG-specific daily analytics with variations.

**Query Parameters**:
- `from_date`: Start date (ISO format, defaults to 30 days ago)
- `to_date`: End date (ISO format, defaults to today)

**Response**:
```json
{
  "bwg_id": "BWG001",
  "period": "2024-12-18 to 2025-01-16",
  "count": 30,
  "analytics": [
    {
      "date": "2025-01-16",
      "variation_percent": 12.5,
      "calculated_quantity_kg": 112.5,
      "created_at": "2025-01-16T00:05:00+00:00"
    }
  ]
}
```

#### GET `/admin/daily-analytics/vehicle-wise/{vehicle_id}`
Get vehicle-specific daily analytics with variations.

**Query Parameters**:
- `from_date`: Start date (ISO format)
- `to_date`: End date (ISO format)

**Response**: Similar to BWG-wise endpoint

#### GET `/admin/daily-analytics/total-processing`
Get total daily processing analytics with variations.

**Query Parameters**:
- `from_date`: Start date (ISO format)
- `to_date`: End date (ISO format)

**Response**:
```json
{
  "type": "total_processing",
  "period": "2024-12-18 to 2025-01-16",
  "count": 30,
  "analytics": [
    {
      "date": "2025-01-16",
      "variation_percent": -8.3,
      "calculated_quantity_kg": 916.7,
      "created_at": "2025-01-16T00:05:00+00:00"
    }
  ]
}
```

#### POST `/admin/daily-analytics/regenerate`
Manually trigger analytics regeneration.

**Query Parameters**:
- `target_date`: Date to regenerate (ISO format, defaults to today)

**Response**:
```json
{
  "success": true,
  "target_date": "2025-01-16",
  "generated": {
    "bwg_count": 45,
    "vehicle_count": 12,
    "total_processing": 1
  }
}
```

## Installation & Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
# or
pip install apscheduler==3.10.4
```

### 2. Run Database Migration
```bash
# Execute the migration SQL
psql -U your_user -d your_database -f migrations/add_daily_processing_analytics.sql
```

### 3. Update Models
The [app/models.py](app/models.py) already includes the new `DailyProcessingAnalytics` model.

### 4. Start Application
```bash
uvicorn app.main:app --reload
```

The scheduler will automatically:
- Initialize on app startup
- Run daily at 00:05 UTC
- Shutdown gracefully on app shutdown

## Usage Examples

### Generate Analytics for Specific Date
```bash
curl -X POST http://localhost:8000/admin/daily-analytics/regenerate?target_date=2025-01-16
```

### Get BWG Wise Analytics (Last 7 Days)
```bash
curl "http://localhost:8000/admin/daily-analytics/bwg-wise/BWG001?from_date=2025-01-10&to_date=2025-01-16"
```

### Get Total Processing Analytics (Last 30 Days)
```bash
curl "http://localhost:8000/admin/daily-analytics/total-processing"
```

## How It Works

### Daily Generation Flow:
```
1. Scheduler triggers at 00:05 UTC
2. For each approved BWG:
   - Get daily_waste_kg from BWG profile
   - Generate 3 random variations (±25%)
   - Calculate quantities: base_qty × (1 + variation%)
   - Store in daily_processing_analytics table
3. For each active vehicle:
   - Get average pickup quantity
   - Generate 3 random variations (±25%)
   - Calculate quantities
   - Store in daily_processing_analytics table
4. For total processing:
   - Sum all pickups for the day
   - Generate 3 random variations (±25%)
   - Calculate quantities
   - Store with null BWG/vehicle IDs
```

### Variation Calculation:
```
Random variation: -0.25 to +0.25 (uniform distribution)
Variation percent: variation × 100 (e.g., -12.5%)
Calculated quantity: base_qty × (1 + variation)

Example:
- Base daily waste: 100 kg
- Random variation: 0.125 (+12.5%)
- Calculated quantity: 100 × (1 + 0.125) = 112.5 kg
```

## Database Schema

### daily_processing_analytics Table
```sql
CREATE TABLE daily_processing_analytics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    bwg_id VARCHAR(10) REFERENCES bwg(id),
    vehicle_id INTEGER REFERENCES vehicles(vehicle_id),
    
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
```

**Indices**: 
- date
- bwg_id  
- vehicle_id
- (date, bwg_id)
- (date, vehicle_id)

## Configuration

### Schedule Time
Edit [app/scheduler.py](app/scheduler.py):
```python
scheduler.add_job(
    ...
    trigger=CronTrigger(hour=0, minute=5),  # Change this
    ...
)
```

**Common times**:
- `hour=0, minute=5`: 00:05 UTC (default)
- `hour=4, minute=0`: 04:00 UTC
- `hour=6, minute=30`: 06:30 UTC

### Variation Range
Edit [app/services/daily_analytics_service.py](app/services/daily_analytics_service.py):
```python
class DailyAnalyticsGenerator:
    VARIATION_MIN = -0.25  # -25%
    VARIATION_MAX = 0.25   # +25%
```

## Testing

### Manual Test
```python
from app.services.daily_analytics_service import DailyAnalyticsGenerator
from datetime import date

# Regenerate for today
stats = DailyAnalyticsGenerator.regenerate_daily_analytics()
print(stats)  # {'bwg_count': 45, 'vehicle_count': 12, 'total_processing': 1}

# Regenerate for specific date
stats = DailyAnalyticsGenerator.regenerate_daily_analytics(date(2025, 1, 16))
```

### API Test
```bash
# Test manual regeneration
curl -X POST http://localhost:8000/admin/daily-analytics/regenerate

# Test fetching analytics
curl "http://localhost:8000/admin/daily-analytics/total-processing"
```

## Troubleshooting

### Issue: Scheduler not running
**Solution**: 
- Check logs for startup errors
- Verify APScheduler is installed: `pip list | grep apscheduler`
- Check scheduler initialization in main.py startup event

### Issue: Analytics not generating
**Solution**:
- Verify database table exists: `SELECT * FROM daily_processing_analytics LIMIT 1;`
- Check if approved BWGs exist: `SELECT COUNT(*) FROM bwg WHERE status='approved';`
- Manually trigger: `POST /admin/daily-analytics/regenerate`
- Check logs for errors

### Issue: Wrong time zone
**Solution**:
- The scheduler uses UTC time
- Convert to local time: Check scheduler initialization
- Edit `hour` and `minute` parameters to match your timezone

## Files Changed/Added

### New Files:
- [app/services/daily_analytics_service.py](app/services/daily_analytics_service.py): Analytics generation service
- [app/scheduler.py](app/scheduler.py): APScheduler initialization
- [migrations/add_daily_processing_analytics.sql](migrations/add_daily_processing_analytics.sql): Database migration

### Modified Files:
- [app/models.py](app/models.py): Added `DailyProcessingAnalytics` model
- [app/main.py](app/main.py): Added scheduler initialization
- [app/routers/admin/reports.py](app/routers/admin/reports.py): Added analytics endpoints
- [requirements.txt](requirements.txt): Added apscheduler dependency
- [req.txt](req.txt): Added apscheduler dependency

## Next Steps

1. **Run Migration**: Execute the SQL migration to create the table
2. **Install Dependencies**: `pip install apscheduler==3.10.4`
3. **Restart Application**: Start the app to initialize the scheduler
4. **Test**: Use the endpoints to verify analytics are being generated

## Support

For issues or questions:
1. Check the logs for detailed error messages
2. Verify database connectivity
3. Ensure all dependencies are installed
4. Test endpoints manually using curl or Postman
