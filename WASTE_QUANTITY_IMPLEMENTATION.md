# Waste Quantity Calculation System - Implementation Guide

## Overview

This document describes the implementation of the dynamic waste quantity calculation system for BWG (Bulk Waste Generator) registrations. The system calculates daily waste quantities based on registered daily average waste, with non-uniform variations and proper handling of missed pickups.

## Business Logic

### Fixed Monthly Quantity
- **Input**: `daily_waste_kg` registered during BWG registration
- **Calculation**: `monthly_quantity = daily_waste_kg × days_in_month`
- **Handles**: Leap years, month-length variations, mid-month onboarding

### Daily Variations
- **Range**: ±25% of the daily average (non-uniform)
- **Method**: Random variations between -25% and +25%
- **Constraint**: Not fixed percentages - each day gets a unique variation (e.g., +7.8%, -14.2%, +18.9%)
- **Guarantee**: Sum of all daily quantities equals the fixed monthly total

### Missed Pickup Handling
- **Logic**: If waste is not picked up on a given day:
  1. That day's quantity is marked as `missed` (quantity = 0)
  2. The quantity is carried forward to the next pickup day
  3. Subsequent pick day receives: `(usual_daily_qty + missed_day_qty)`
  4. Monthly total remains unchanged

## Components

### 1. Waste Calculator Service
**File**: `app/services/waste_calculator.py`

#### Main Class: `WasteQuantityCalculator`

```python
calculator = WasteQuantityCalculator(daily_waste_kg=100.0)
```

#### Key Methods:

##### `generate_daily_quantities(start_date, end_date, missed_dates)`
Generate daily quantities for a date range with optional missed pickup tracking.

```python
quantities = calculator.generate_daily_quantities(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 1, 31),
    missed_dates=[date(2024, 1, 5), date(2024, 1, 12)]  # Optional
)

# Returns: Dict[date, Dict]
# {
#     date(2024, 1, 1): {
#         'quantity_kg': 95.23,
#         'variation_percent': -4.8,
#         'is_missed': False,
#         'carried_from_date': None
#     },
#     date(2024, 1, 5): {
#         'quantity_kg': 0.0,
#         'variation_percent': 0.0,
#         'is_missed': True,
#         'carried_from_date': None
#     },
#     date(2024, 1, 6): {
#         'quantity_kg': 198.45,  # Includes carried-over from 1/5
#         'variation_percent': 8.2,
#         'is_missed': False,
#         'carried_from_date': date(2024, 1, 5)
#     }
# }
```

##### `generate_month_quantities(target_date, missed_dates)`
Generate quantities for the entire month containing the target date.

```python
monthly = calculator.generate_month_quantities(
    target_date=date(2024, 3, 15),
    missed_dates=[date(2024, 3, 10)]
)
# Returns: Dict[date, Dict] for all days in March 2024
```

##### `get_quantity_for_date(target_date, missed_dates)`
Get the calculated quantity for a specific date.

```python
quantity_data = calculator.get_quantity_for_date(
    target_date=date(2024, 2, 14),
    missed_dates=[date(2024, 2, 10)]
)
# Returns: {
#     'quantity_kg': 107.45,
#     'variation_percent': +7.4,
#     'is_missed': False,
#     'carried_from_date': None
# }
```

##### `calculate_month_summary(target_date, missed_dates)`
Get comprehensive monthly statistics.

```python
summary = calculator.calculate_month_summary(date(2024, 4, 15))
# Returns: {
#     'month': 'April 2024',
#     'fixed_monthly_quantity_kg': 3000.0,
#     'actual_total_quantity_kg': 3000.0,
#     'days_in_month': 30,
#     'pickup_days': 29,
#     'missed_days': 1,
#     'average_variation_percent': 1.2,
#     'min_variation_percent': -24.8,
#     'max_variation_percent': 23.7
# }
```

### 2. Database Schema Updates

#### New Columns in `pickups` Table:
- `quantity_kg` (NUMERIC 12,2): Calculated waste quantity for this pickup
- `variation_percent` (NUMERIC 5,1): Variation from daily average
- `is_missed` (BOOLEAN): Whether pickup was missed
- `carried_from_date` (DATE): Previous missed date (if applicable)

#### Migration:
Run `migrations/add_waste_quantity_columns.sql` to add these columns.

### 3. Model Updates

#### Updated `Pickup` Model
In `app/models.py`, the `Pickup` class now includes:
```python
quantity_kg = Column(Numeric(12, 2))
variation_percent = Column(Numeric(5, 1))
is_missed = Column(Boolean, default=False)
carried_from_date = Column(Date)
```

## API Endpoints

### 1. Enhanced Reports Endpoint
**GET** `/admin/full-report-data`

Returns all collection data with calculated waste quantities enriched.

**Response includes**:
```json
{
    "date": "2024-01-15",
    "daily_waste_kg": 100.0,
    "pickup_quantity_kg": 95.23,
    "quantity_variation_percent": -4.8,
    "is_missed_pickup": false,
    ...
}
```

### 2. New BWG Quantity Analytics Endpoint
**GET** `/admin/reports/bwg-quantity-analytics/{bwg_id}`

Get detailed quantity analytics for a specific BWG.

**Query Parameters**:
- `year`: Year for calculation (default: current year)
- `month`: Month for calculation (default: current month)

**Response**:
```json
{
    "bwg_id": "BWG001",
    "bwg_name": "ABC Organization",
    "daily_waste_kg": 100.0,
    "year": 2024,
    "month": 3,
    "month_name": "March 2024",
    "days_in_month": 31,
    "fixed_monthly_quantity_kg": 3100.0,
    "actual_total_quantity_kg": 3100.0,
    "pickup_days": 30,
    "missed_days": 1,
    "daily_breakdown": {
        "2024-03-01": {
            "quantity_kg": 98.50,
            "variation_percent": -1.5,
            "is_missed": false,
            "carried_from_date": null,
            "status": "CALCULATED"
        },
        "2024-03-05": {
            "quantity_kg": 0.0,
            "variation_percent": 0.0,
            "is_missed": true,
            "carried_from_date": null,
            "status": "CALCULATED"
        },
        "2024-03-06": {
            "quantity_kg": 207.80,
            "variation_percent": 4.2,
            "is_missed": false,
            "carried_from_date": "2024-03-05",
            "status": "CALCULATED"
        }
    }
}
```

### 3. Waste Quantity Metrics Endpoint
**GET** `/admin/waste-quantity-metrics`

Get aggregated waste quantity metrics by period.

**Query Parameters**:
- `period`: daily, weekly, monthly, yearly (default: daily)
- `from_`: Start date (ISO format)
- `to`: End date (ISO format)

**Response**:
```json
{
    "period": "daily",
    "data": [
        {
            "period": "2024-03-15",
            "pickup_count": 25,
            "actual_quantity_kg": 2500.0,
            "successful_pickups": 24,
            "missed_pickups": 1,
            "avg_variation_percent": 2.3,
            "expected_quantity_kg": 2500.0,
            "variance_kg": 0.0,
            "variance_percent": 0.0
        }
    ]
}
```

## Usage Examples

### Python Integration

```python
from app.services.waste_calculator import get_waste_calculator
from datetime import date

# Create calculator for a BWG with 100 kg daily waste
calculator = get_waste_calculator(100.0)

# Get March 2024 quantities
march_data = calculator.generate_month_quantities(date(2024, 3, 15))

# Check specific day
day_qty = march_data.get(date(2024, 3, 10))
print(f"March 10: {day_qty['quantity_kg']} kg ({day_qty['variation_percent']:+.1f}%)")

# Get monthly summary
summary = calculator.calculate_month_summary(date(2024, 3, 15))
print(f"Month: {summary['month']}")
print(f"Total: {summary['actual_total_quantity_kg']} kg")
print(f"Days: {summary['pickup_days']} successful, {summary['missed_days']} missed")
```

### REST API Integration

```javascript
// Get BWG quantity analytics
async function getBWGAnalytics(bwgId, year, month) {
    const response = await fetch(
        `/admin/reports/bwg-quantity-analytics/${bwgId}?year=${year}&month=${month}`
    );
    return response.json();
}

// Get waste metrics for a period
async function getWasteMetrics(period, fromDate, toDate) {
    const response = await fetch(
        `/admin/waste-quantity-metrics?period=${period}&from_=${fromDate}&to=${toDate}`
    );
    return response.json();
}
```

## Testing

### Run the Test Suite

```bash
cd oribackend
python test_waste_calculator.py
```

**Tests include**:
1. Basic daily quantity calculation
2. Leap year handling (February 29 vs 28)
3. Variation range validation (±25%)
4. Missed pickup carry-forward logic
5. Monthly summary statistics
6. Non-uniform variation verification

### Manual Testing

```python
from datetime import date
from app.services.waste_calculator import get_waste_calculator

# Test with 50 kg daily waste
calc = get_waste_calculator(50.0)

# Generate February 2024 (leap year - 29 days)
feb_quantities = calc.generate_month_quantities(date(2024, 2, 15))
total = sum(q['quantity_kg'] for q in feb_quantities.values())
expected = 50.0 * 29  # = 1450 kg

print(f"Expected: {expected}")
print(f"Actual: {total}")
assert abs(total - expected) < 0.01, "Total mismatch!"
```

## Key Features

✅ **Accurate Calculations**: Sum of daily quantities always equals fixed monthly total
✅ **Non-uniform Variations**: Each day gets unique variation percentage
✅ **Missed Pickup Handling**: Quantities properly carried forward
✅ **Leap Year Support**: Correctly handles February 29
✅ **Month Flexibility**: Works with all month lengths
✅ **Range Compliance**: All variations within ±25%
✅ **Database Integration**: New pickup columns track all data
✅ **Analytics Ready**: Comprehensive endpoints for reporting

## Integration Checklist

- [ ] Run migration: `add_waste_quantity_columns.sql`
- [ ] Update database schema
- [ ] Test waste calculator with test suite
- [ ] Deploy updated models
- [ ] Enable new API endpoints
- [ ] Update frontend to display quantity metrics
- [ ] Configure admin analytics dashboard
- [ ] Monitor API performance

## Notes

- All calculations are deterministic within the same execution but randomized across executions for non-uniform variation
- For consistent testing, seed the random number generator if needed
- The calculator works with any positive daily_waste_kg value
- Missed dates should be validated against actual pickup status in the database
- Monthly calculations can be cached if performance optimization is needed
