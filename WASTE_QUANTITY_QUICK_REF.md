# Waste Quantity System - Quick Reference

## Calculation Formula

```
FIXED_MONTHLY = daily_waste_kg × days_in_month

For each day:
  variation = random(-25%, +25%)
  daily_quantity = daily_waste_kg × (1 + variation)
  
  If day is missed:
    quantity[day] = 0, is_missed = true
    quantity[next_day] += daily_waste_kg (carry forward)

SUM(all daily quantities) MUST = FIXED_MONTHLY
```

## Key Classes

### WasteQuantityCalculator
```python
from app.services.waste_calculator import WasteQuantityCalculator

calc = WasteQuantityCalculator(daily_waste_kg=100.0)

# Methods:
calc.generate_daily_quantities(start, end, missed_dates)    # Dict[date, qty_data]
calc.generate_month_quantities(target_date, missed_dates)   # Dict[date, qty_data]
calc.get_quantity_for_date(target_date, missed_dates)       # qty_data
calc.calculate_month_summary(target_date, missed_dates)     # summary_dict
```

### Helper Functions
```python
from app.services.waste_quantity_helpers import *

get_bwg_daily_waste(bwg_id)                                    # float
calculate_and_update_pickup_quantity(bwg_id, date, missed)    # qty_data
update_monthly_quantities(bwg_id, year, month)                # result_dict
handle_missed_pickup(bwg_id, missed_date)                     # result_dict
get_month_pickup_status(bwg_id, year, month)                  # status_dict
```

## Quantity Data Structure

```python
{
    'quantity_kg': 95.23,                    # float
    'variation_percent': -4.8,               # float (e.g., +7.8, -14.2)
    'is_missed': False,                      # bool
    'carried_from_date': None                # date or None
}
```

## Database Columns (pickups table)

| Column | Type | Description |
|--------|------|-------------|
| quantity_kg | NUMERIC(12,2) | Calculated waste amount in kg |
| variation_percent | NUMERIC(5,1) | Variation from daily average (-25 to +25) |
| is_missed | BOOLEAN | Whether pickup was missed |
| carried_from_date | DATE | Previous missed date (if applicable) |

## API Endpoints

### Get Full Report with Quantities
```
GET /admin/full-report-data
```
Returns all collection data with calculated quantities.

### Get BWG Quantity Analytics
```
GET /admin/reports/bwg-quantity-analytics/{bwg_id}?year=2024&month=3
```
Detailed analytics for a specific BWG and month.

### Get Waste Metrics
```
GET /admin/waste-quantity-metrics?period=daily&from_=2024-03-01&to=2024-03-31
```
Aggregated metrics with variance analysis.

## Common Tasks

### Get All Daily Quantities for a Month
```python
from app.services.waste_calculator import get_waste_calculator
from datetime import date

calc = get_waste_calculator(100.0)  # 100 kg daily waste
monthly = calc.generate_month_quantities(date(2024, 3, 15))

for day, qty_data in monthly.items():
    print(f"{day}: {qty_data['quantity_kg']} kg")
```

### Update Pickups After Recording Missed Pickup
```python
from app.services.waste_quantity_helpers import handle_missed_pickup, update_monthly_quantities
from datetime import date

# Mark as missed
result = handle_missed_pickup('BWG001', date(2024, 3, 5))

# Recalculate entire month
summary = update_monthly_quantities('BWG001', 2024, 3)
```

### Get Current Month Status for a BWG
```python
from app.services.waste_quantity_helpers import get_month_pickup_status
from datetime import datetime

today = datetime.now()
status = get_month_pickup_status('BWG001', today.year, today.month)

print(f"Fixed monthly: {status['fixed_monthly_quantity_kg']} kg")
print(f"Actual total: {status['actual_total_quantity_kg']} kg")
print(f"Successful pickups: {status['successful_pickups']}")
print(f"Missed pickups: {status['missed_pickups']}")
```

### Query by API
```javascript
// Get analytics for March 2024
fetch('/admin/reports/bwg-quantity-analytics/BWG001?year=2024&month=3')
  .then(r => r.json())
  .then(data => {
    console.log(`${data.month_name}: ${data.actual_total_quantity_kg} kg`);
    data.daily_breakdown.forEach(day => {
      console.log(`${day.date}: ${day.quantity_kg} kg (${day.variation_percent:+.1f}%)`);
    });
  });

// Get monthly metrics
fetch('/admin/waste-quantity-metrics?period=monthly&from_=2024-01-01&to_=2024-12-31')
  .then(r => r.json())
  .then(data => {
    data.data.forEach(metric => {
      console.log(`${metric.period}: ${metric.actual_quantity_kg} kg`);
    });
  });
```

## Testing

```bash
# Run full test suite
python test_waste_calculator.py

# Test specific calculation
python -c "
from app.services.waste_calculator import get_waste_calculator
from datetime import date

calc = get_waste_calculator(100.0)
month = calc.generate_month_quantities(date(2024, 1, 15))
total = sum(q['quantity_kg'] for q in month.values())
print(f'Total: {total}, Expected: 3100.0, Match: {abs(total - 3100.0) < 0.01}')
"
```

## Validation Checklist

- [ ] Migration applied to database
- [ ] New Pickup model columns present
- [ ] API endpoints returning quantity data
- [ ] Variations all within ±25%
- [ ] Monthly totals match formula
- [ ] Missed pickups carry forward correctly
- [ ] Leap year handling works
- [ ] Frontend displays quantities

## Troubleshooting

### Quantities not calculated
- Check if `daily_waste_kg` is set in BWG registration
- Verify migration was applied
- Check for errors in calculator initialization

### Sum doesn't equal fixed monthly
- Ensure no rounding errors (should be < 0.01 kg difference)
- Check missed_dates parameter is correct
- Verify days_in_month calculation

### Variation out of range
- Check random number generation
- Verify adjustment factor calculation
- Review variation bounds (-0.25 to +0.25)

### Missed pickup not carrying forward
- Confirm `is_missed` flag set correctly
- Check `carried_from_date` is populated
- Verify next pickup exists in database

## Performance Tips

1. **Cache calculations** for frequently accessed months
2. **Batch updates** when updating multiple pickups
3. **Use indexes** on `pickups(bwg_id, scheduled_date)`
4. **Limit date ranges** in API queries
5. **Consider pre-calculating** at month-end

## Notes

- All calculations use Decimal for precision
- Variations are randomized - different runs will produce different results
- For testing, seed `random` if deterministic output needed
- Month calculations are CPU-light, suitable for real-time generation
- Database updates should be transactional
