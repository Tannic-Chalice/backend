# BWG Collection Reports Daily Generation Implementation

## Overview
Automated daily generation of BWG collection reports with ±25% waste quantity variations. Each unique BWG receives one new report row per day containing calculated wet and dry waste quantities.

## Features Implemented

### 1. BwgCollectionReportGenerator Service Class
**File**: `app/services/daily_analytics_service.py` (Lines 366-505)

Creates daily collection reports for all approved BWGs with ±25% random waste variations.

**Key Method**:
- `generate_collection_reports_for_date(target_date=None)` - Generates/updates collection reports for a specific date
  - Queries all approved BWGs with `daily_waste_kg > 0`
  - Generates ±25% random variation per BWG
  - Calculates wet waste (60%) and dry waste (40%) by default
  - Uses BWG's configured wet/dry ratio if available
  - Creates or updates `bwg_collection_report` table records
  - Returns dictionary with `{'created': int, 'updated': int}`

### 2. BwgCollectionReport Model
**File**: `app/models.py` (Lines 259-276)

ORM model mapping to existing `bwg_collection_report` table.

**Table Schema**:
```sql
- bwg_id (INT, FK)
- bwg_name (VARCHAR)
- date (DATE)
- corporation (VARCHAR)
- ward_info (VARCHAR)
- wet_waste_kg (NUMERIC)
- dry_waste_kg (NUMERIC)
- vehicle_no (VARCHAR, NULL)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

### 3. Daily Scheduler Integration
**File**: `app/scheduler.py` (Lines 20-37)

Updated scheduler to run both analytics and BWG collection reports daily.

**Execution**:
- Time: 00:05 UTC daily
- Function: `trigger_daily_tasks()`
- Includes:
  1. `DailyAnalyticsGenerator.regenerate_daily_analytics()`
  2. `BwgCollectionReportGenerator.generate_collection_reports_for_date()`

### 4. REST API Endpoints
**File**: `app/routers/admin/reports.py` (Lines 573-760)

Five new endpoints for BWG collection reports:

#### A. GET `/admin/bwg-collection-reports`
Fetch collection reports with optional date range and BWG filtering.

**Query Parameters**:
- `from_date` (ISO format, default: 30 days ago)
- `to_date` (ISO format, default: today)
- `bwg_id` (optional, filter by specific BWG)

**Response**:
```json
{
  "from_date": "2026-01-17",
  "to_date": "2026-01-18",
  "total_records": 45,
  "reports": [
    {
      "id": 1,
      "bwg_id": 101,
      "bwg_name": "ABC Organization",
      "date": "2026-01-18",
      "corporation": "Zone A",
      "ward_info": "Ward 5",
      "wet_waste_kg": 150.50,
      "dry_waste_kg": 100.25,
      "total_waste_kg": 250.75,
      "vehicle_no": null
    }
  ]
}
```

#### B. GET `/admin/bwg-collection-reports/{bwg_id}`
Fetch collection reports for a specific BWG.

**Response Includes**:
- BWG details (name, corporation, ward_info)
- All reports for date range
- Calculated totals

#### C. POST `/admin/bwg-collection-reports/regenerate`
Manually trigger report regeneration.

**Query Parameters**:
- `target_date` (ISO format, default: today)

**Response**:
```json
{
  "success": true,
  "target_date": "2026-01-18",
  "created": 42,
  "updated": 3,
  "total": 45
}
```

#### D. GET `/admin/bwg-collection-reports/daily-summary/{date}`
Fetch daily summary of all BWG collection reports.

**Response**:
```json
{
  "date": "2026-01-18",
  "bwg_count": 45,
  "total_wet_waste": 6750.50,
  "total_dry_waste": 4500.25,
  "total_waste": 11250.75,
  "reports": [...]
}
```

#### E. Existing Endpoints Updated
- `POST /admin/daily-analytics/regenerate` - Now triggers both analytics and BWG reports

## Waste Calculation Logic

### Default Wet/Dry Split (60%/40%)
```
Base Waste = daily_waste_kg × (1 + variation)
Where variation ∈ [-0.25, 0.25] (uniform random)

Wet Waste = Base Waste × 0.60
Dry Waste = Base Waste × 0.40
```

### Custom Wet/Dry Ratio
If BWG has configured `wet_waste_kg` and `dry_waste_kg`:
```
Configured Ratio = wet_waste_kg / (wet_waste_kg + dry_waste_kg)

Wet Waste = Base Waste × Configured Ratio
Dry Waste = Base Waste × (1 - Configured Ratio)
```

## Daily Execution Flow

**Time**: 00:05 UTC (configurable in `scheduler.py`)

**Process**:
1. Scheduler triggers `trigger_daily_tasks()`
2. Executes `DailyAnalyticsGenerator.regenerate_daily_analytics()`
3. Executes `BwgCollectionReportGenerator.generate_collection_reports_for_date()`
4. Logs completion statistics

**Example Log Output**:
```
INFO:     Triggering daily tasks...
INFO:     Daily analytics regenerated: {'bwg_wise': 45, 'vehicle_wise': 12, 'total_processing': 1}
INFO:     BWG collection reports generated: {'created': 42, 'updated': 3}
INFO:     Manual generation completed - Analytics: {...}, BWG Reports: {'created': 42, 'updated': 3}
```

## Manual Regeneration

### Option 1: Use API Endpoint
```bash
# Regenerate for today
POST /admin/bwg-collection-reports/regenerate

# Regenerate for specific date
POST /admin/bwg-collection-reports/regenerate?target_date=2026-01-15
```

### Option 2: Use Trigger Function
```python
from app.scheduler import trigger_daily_analytics

result = trigger_daily_analytics('2026-01-15')
# Returns: {'analytics': {...}, 'bwg_reports': {'created': int, 'updated': int}}
```

## Database Considerations

### Query Performance
- Recommended indices on `bwg_collection_report`:
  - `(bwg_id, date)` - For BWG-specific reports
  - `(date)` - For daily summaries
  - `(corporation)` - For zone-wise filtering
  - `(ward_info)` - For ward-wise filtering

### Data Retention
- Reports are created/updated daily
- Historical data persists for trend analysis
- Duplicate prevention: Updates if record exists for BWG+Date combination

## Configuration

### Scheduler Time
**File**: `app/scheduler.py` (Line 49)
```python
trigger=CronTrigger(hour=0, minute=5)  # Change hour/minute as needed
```

### Variation Range
**File**: `app/services/daily_analytics_service.py` (Lines 372-373)
```python
VARIATION_MIN = -0.25  # -25%
VARIATION_MAX = 0.25   # +25%
```

### Wet/Dry Split Ratio
**File**: `app/services/daily_analytics_service.py` (Lines 408-409)
```python
wet_waste = total_waste * 0.60
dry_waste = total_waste * 0.40
```

## Error Handling

### Graceful Degradation
- Individual BWG failures don't stop batch processing
- Detailed logging for each BWG processed
- Failed records logged but don't halt entire job

### Logging
- Success/Failure of each BWG recorded
- Summary statistics logged after batch completion
- Error traces for debugging

## Testing

### Manual Test Endpoint
```bash
curl -X POST "http://localhost:8000/admin/bwg-collection-reports/regenerate?target_date=2026-01-18"
```

### View Generated Reports
```bash
curl -X GET "http://localhost:8000/admin/bwg-collection-reports?from_date=2026-01-17&to_date=2026-01-18"
```

### View Daily Summary
```bash
curl -X GET "http://localhost:8000/admin/bwg-collection-reports/daily-summary/2026-01-18"
```

## Files Modified

1. **app/services/daily_analytics_service.py**
   - Added `BwgCollectionReportGenerator` class (140 lines)
   - Added `get_bwg_collection_report_generator()` factory function

2. **app/scheduler.py**
   - Updated `trigger_daily_tasks()` function (new)
   - Modified scheduler job to call `trigger_daily_tasks()`
   - Modified `trigger_daily_analytics()` to include BWG reports

3. **app/routers/admin/reports.py**
   - Added 5 new API endpoints (188 lines)
   - Updated imports to include `BwgCollectionReportGenerator`

4. **app/models.py**
   - Added `BwgCollectionReport` model (18 lines)

## Verification Steps

1. ✅ Application starts without import errors
2. ✅ Scheduler initializes and logs "Daily Tasks (Analytics + BWG Reports)"
3. ✅ API endpoints accessible
4. ✅ Manual regeneration can be triggered
5. ✅ Database records created/updated as expected
6. ✅ Daily execution at 00:05 UTC (scheduler logs next run time)

## Known Limitations & Future Enhancements

### Current Limitations
- Vehicle assignment: Currently set to `NULL`, can be populated if mapping logic added
- Timezone handling: Uses UTC/server timezone for "today" date

### Potential Enhancements
- Batch API endpoint to regenerate multiple dates
- Filtering by waste type (wet/dry)
- Historical trend analysis endpoints
- Email notifications of daily summaries
- Configurable wet/dry ratios per zone/corporation
