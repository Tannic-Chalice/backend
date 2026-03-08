"""
Test script for Waste Quantity Calculator

Tests the waste quantity calculation logic including:
- Daily variation within ±25%
- Monthly total matching fixed quantity
- Missed pickup handling
- Month length variations
"""

import sys
from datetime import date, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.waste_calculator import get_waste_calculator


def test_basic_calculation():
    """Test basic daily quantity calculation"""
    print("\n" + "="*60)
    print("TEST 1: Basic Daily Quantity Calculation")
    print("="*60)
    
    daily_waste = 100.0  # kg
    calculator = get_waste_calculator(daily_waste)
    
    # Test for January (31 days)
    test_date = date(2024, 1, 15)
    quantities = calculator.generate_month_quantities(test_date)
    
    total = sum(q['quantity_kg'] for q in quantities.values())
    expected = daily_waste * 31
    
    print(f"Daily waste: {daily_waste} kg")
    print(f"Month: January 2024 (31 days)")
    print(f"Expected monthly total: {expected} kg")
    print(f"Calculated monthly total: {total} kg")
    print(f"Match: {'✓ PASS' if abs(total - expected) < 0.01 else '✗ FAIL'}")
    
    # Show sample variations
    print(f"\nSample daily variations (first 5 days):")
    for day, (pickup_date, qty_data) in enumerate(list(quantities.items())[:5], 1):
        print(f"  {pickup_date}: {qty_data['quantity_kg']} kg ({qty_data['variation_percent']:+.1f}%)")


def test_leap_year():
    """Test February in leap year vs non-leap year"""
    print("\n" + "="*60)
    print("TEST 2: Leap Year Handling")
    print("="*60)
    
    daily_waste = 50.0  # kg
    calculator = get_waste_calculator(daily_waste)
    
    # February 2024 (leap year - 29 days)
    leap_date = date(2024, 2, 15)
    leap_quantities = calculator.generate_month_quantities(leap_date)
    leap_total = sum(q['quantity_kg'] for q in leap_quantities.values())
    leap_expected = daily_waste * 29
    
    # February 2023 (non-leap - 28 days)
    non_leap_date = date(2023, 2, 15)
    non_leap_quantities = calculator.generate_month_quantities(non_leap_date)
    non_leap_total = sum(q['quantity_kg'] for q in non_leap_quantities.values())
    non_leap_expected = daily_waste * 28
    
    print(f"Daily waste: {daily_waste} kg")
    print(f"\nFebruary 2024 (LEAP YEAR - 29 days):")
    print(f"  Expected: {leap_expected} kg")
    print(f"  Calculated: {leap_total} kg")
    print(f"  Match: {'✓ PASS' if abs(leap_total - leap_expected) < 0.01 else '✗ FAIL'}")
    
    print(f"\nFebruary 2023 (NON-LEAP - 28 days):")
    print(f"  Expected: {non_leap_expected} kg")
    print(f"  Calculated: {non_leap_total} kg")
    print(f"  Match: {'✓ PASS' if abs(non_leap_total - non_leap_expected) < 0.01 else '✗ FAIL'}")


def test_variation_range():
    """Test that all variations are within ±25%"""
    print("\n" + "="*60)
    print("TEST 3: Variation Range Check (±25%)")
    print("="*60)
    
    daily_waste = 100.0  # kg
    calculator = get_waste_calculator(daily_waste)
    
    test_date = date(2024, 3, 15)
    quantities = calculator.generate_month_quantities(test_date)
    
    min_var = float('inf')
    max_var = float('-inf')
    violations = 0
    
    for qty_data in quantities.values():
        if not qty_data['is_missed']:
            var = qty_data['variation_percent']
            min_var = min(min_var, var)
            max_var = max(max_var, var)
            
            if var < -25.0 or var > 25.0:
                violations += 1
    
    print(f"Daily waste: {daily_waste} kg")
    print(f"Month: March 2024")
    print(f"Min variation: {min_var:.1f}%")
    print(f"Max variation: {max_var:.1f}%")
    print(f"Within ±25% range: {min_var >= -25.0 and max_var <= 25.0}")
    print(f"Variations out of range: {violations}")
    print(f"Result: {'✓ PASS' if violations == 0 else '✗ FAIL'}")


def test_missed_pickups():
    """Test handling of missed pickups"""
    print("\n" + "="*60)
    print("TEST 4: Missed Pickup Handling")
    print("="*60)
    
    daily_waste = 100.0  # kg
    calculator = get_waste_calculator(daily_waste)
    
    test_date = date(2024, 4, 15)
    missed_dates = [date(2024, 4, 5), date(2024, 4, 10)]
    
    quantities = calculator.generate_month_quantities(test_date, missed_dates)
    
    # Find which days got the carried-over quantity
    print(f"Daily waste: {daily_waste} kg")
    print(f"Month: April 2024")
    print(f"Missed pickup dates: {missed_dates}")
    
    carried_forward = []
    for pickup_date, qty_data in quantities.items():
        if qty_data['carried_from_date']:
            carried_forward.append(pickup_date)
            print(f"\n{pickup_date}:")
            print(f"  Quantity: {qty_data['quantity_kg']} kg")
            print(f"  Carried from: {qty_data['carried_from_date']}")
    
    total = sum(q['quantity_kg'] for q in quantities.values())
    expected = daily_waste * 30  # April has 30 days
    
    print(f"\nTotal monthly quantity: {total} kg")
    print(f"Expected: {expected} kg")
    print(f"Match: {'✓ PASS' if abs(total - expected) < 0.01 else '✗ FAIL'}")


def test_month_summary():
    """Test monthly summary statistics"""
    print("\n" + "="*60)
    print("TEST 5: Monthly Summary Statistics")
    print("="*60)
    
    daily_waste = 75.0  # kg
    calculator = get_waste_calculator(daily_waste)
    
    test_date = date(2024, 5, 15)
    summary = calculator.calculate_month_summary(test_date)
    
    print(f"Month: {summary['month']}")
    print(f"Daily waste registration: {daily_waste} kg")
    print(f"Days in month: {summary['days_in_month']}")
    print(f"\nFixed monthly quantity: {summary['fixed_monthly_quantity_kg']} kg")
    print(f"Actual total quantity: {summary['actual_total_quantity_kg']} kg")
    print(f"Pickup days: {summary['pickup_days']}")
    print(f"Missed days: {summary['missed_days']}")
    print(f"\nVariation statistics:")
    print(f"  Average: {summary['average_variation_percent']}%")
    print(f"  Min: {summary['min_variation_percent']}%")
    print(f"  Max: {summary['max_variation_percent']}%")
    print(f"\nTotal match: {'✓ PASS' if abs(summary['fixed_monthly_quantity_kg'] - summary['actual_total_quantity_kg']) < 0.01 else '✗ FAIL'}")


def test_non_uniform_variation():
    """Test that variations are non-uniform"""
    print("\n" + "="*60)
    print("TEST 6: Non-Uniform Variation Check")
    print("="*60)
    
    daily_waste = 100.0  # kg
    calculator = get_waste_calculator(daily_waste)
    
    test_date = date(2024, 6, 15)
    quantities = calculator.generate_month_quantities(test_date)
    
    variations = [q['variation_percent'] for q in quantities.values() if not q['is_missed']]
    
    print(f"Checking if variations are non-uniform (different values)...")
    print(f"Total variations collected: {len(variations)}")
    print(f"Unique variation values: {len(set(variations))}")
    print(f"\nSample variations (first 15):")
    for i, var in enumerate(variations[:15], 1):
        print(f"  Day {i}: {var:+.1f}%")
    
    # Check if we have good variation
    unique_count = len(set(variations))
    is_non_uniform = unique_count > len(variations) * 0.7  # At least 70% unique
    
    print(f"\nIs non-uniform: {'✓ PASS' if is_non_uniform else '✗ FAIL'}")


def main():
    """Run all tests"""
    print("\n" + "#"*60)
    print("# WASTE QUANTITY CALCULATOR - COMPREHENSIVE TEST SUITE")
    print("#"*60)
    
    try:
        test_basic_calculation()
        test_leap_year()
        test_variation_range()
        test_missed_pickups()
        test_month_summary()
        test_non_uniform_variation()
        
        print("\n" + "#"*60)
        print("# ALL TESTS COMPLETED")
        print("#"*60 + "\n")
        
    except Exception as e:
        print(f"\n✗ TEST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
