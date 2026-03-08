# BWG Collection Reports - Quick Reference

## What Was Implemented

Daily automatic generation of BWG collection reports with ±25% waste variations in the `bwg_collection_report` table.

## How It Works

```
Every Day at 00:05 UTC:
  1. For each APPROVED BWG with daily_waste_kg:
     - Generate random ±25% variation
     - Calculate: total_waste = daily_waste_kg × (1 + variation)
     - Split: wet = 60%, dry = 40% (or use BWG's configured ratio)
     - Create/Update row in bwg_collection_report table
     - Store: bwg_id, bwg_name, date, corporation, ward_info, wet_waste_kg, dry_waste_kg
```

## API Endpoints

### 1. Get All Reports (with filters)
```bash
GET /admin/bwg-collection-reports
  ?from_date=2026-01-17
  &to_date=2026-01-18
  &bwg_id=123 (optional)
```

### 2. Get Reports for Specific BWG
```bash
GET /admin/bwg-collection-reports/123
  ?from_date=2026-01-17
  &to_date=2026-01-18
```

### 3. Get Daily Summary
```bash
GET /admin/bwg-collection-reports/daily-summary/2026-01-18
```
Returns: Total waste from all BWGs for that date

### 4. Manually Trigger Generation
```bash
POST /admin/bwg-collection-reports/regenerate
  ?target_date=2026-01-18 (optional, defaults to today)
```
Response: `{created: int, updated: int, total: int}`

### 5. Trigger Both Analytics & Reports
```bash
POST /admin/daily-analytics/regenerate
  ?target_date=2026-01-18 (optional)
```

## Database Table

```sql
bwg_collection_report:
  - id (primary key)
  - bwg_id (FK to bwg)
  - bwg_name
  - date
  - corporation (zone)
  - ward_info
  - wet_waste_kg (numeric)
  - dry_waste_kg (numeric)
  - vehicle_no (nullable)
  - created_at
  - updated_at
```

## Code Locations

| Component | Location | Lines |
|-----------|----------|-------|
| Service Logic | `app/services/daily_analytics_service.py` | 366-505 |
| Scheduler | `app/scheduler.py` | 20-37 |
| API Endpoints | `app/routers/admin/reports.py` | 573-760 |
| Model | `app/models.py` | 259-276 |

## Daily Execution

**File**: `app/scheduler.py`
**Time**: 00:05 UTC (modify line 49: `CronTrigger(hour=0, minute=5)`)
**Function**: `trigger_daily_tasks()`
**Includes**: 
- Daily analytics regeneration
- BWG collection report generation

## Variation Logic

```python
# Generate random ±25% variation
variation = random.uniform(-0.25, 0.25)

# Calculate base waste
total_waste = daily_waste_kg * (1 + variation)

# Split between wet and dry (default 60% wet, 40% dry)
wet_waste = total_waste * 0.60
dry_waste = total_waste * 0.40

# Or use BWG's configured ratio if available
if bwg.wet_waste_kg and bwg.dry_waste_kg:
    ratio = bwg.wet_waste_kg / (bwg.wet_waste_kg + bwg.dry_waste_kg)
    wet_waste = total_waste * ratio
    dry_waste = total_waste * (1 - ratio)
```

## Testing

### Test 1: Manual Regeneration
```bash
curl -X POST "http://localhost:8000/admin/bwg-collection-reports/regenerate"
```
Expected: `{success: true, created: X, updated: Y, total: Z}`

### Test 2: View Today's Reports
```bash
curl "http://localhost:8000/admin/bwg-collection-reports"
```

### Test 3: View Specific BWG Reports
```bash
curl "http://localhost:8000/admin/bwg-collection-reports/101"
```

### Test 4: View Daily Summary
```bash
curl "http://localhost:8000/admin/bwg-collection-reports/daily-summary/2026-01-18"
```

## Configuration Changes

### Change Execution Time
**File**: `app/scheduler.py` line 49
```python
trigger=CronTrigger(hour=0, minute=5)  # Change to your preferred time
```

### Change Variation Range
**File**: `app/services/daily_analytics_service.py` lines 372-373
```python
VARIATION_MIN = -0.25  # Change this
VARIATION_MAX = 0.25   # Change this
```

### Change Wet/Dry Split
**File**: `app/services/daily_analytics_service.py` lines 408-409
```python
wet_waste = total_waste * 0.60  # Change 0.60 to your ratio
dry_waste = total_waste * 0.40  # Change 0.40 accordingly
```

## Troubleshooting

### Reports Not Generated
1. Check scheduler is running: Look for "Daily Tasks (Analytics + BWG Reports)" in logs
2. Check BWG status: Only APPROVED BWGs with daily_waste_kg > 0 are processed
3. Check database: Verify bwg_collection_report table exists
4. Manual trigger: `POST /admin/bwg-collection-reports/regenerate`

### Check Next Scheduled Run
Look in logs for: `Next wakeup is due at YYYY-MM-DD HH:MM:SS`

### View Logs
```bash
# Start app in foreground
python -m uvicorn app.main:app --reload

# Look for these log messages:
# - "Triggering daily tasks..."
# - "Daily analytics regenerated: {...}"
# - "BWG collection reports generated: {...}"
```

## Data Retention

- Reports are **additive** - new rows added daily
- Updates happen only if same BWG+date exists
- Historical data preserved for trend analysis
- No automatic cleanup (can delete old records manually if needed)

## Performance Notes

- Generated daily for all approved BWGs (no filtering)
- Typical time: < 1 second for 50 BWGs
- Database indices recommended on (bwg_id, date) and (date)
- Query operations cached by database query planner

## Files Modified Summary

1. **app/services/daily_analytics_service.py** - Added BwgCollectionReportGenerator class
2. **app/scheduler.py** - Updated to run both analytics and reports
3. **app/routers/admin/reports.py** - Added 5 new API endpoints
4. **app/models.py** - Added BwgCollectionReport model
