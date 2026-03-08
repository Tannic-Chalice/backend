"""
Waste Quantity Calculator Service

Handles:
- Calculation of daily waste quantities with ±25% variation
- Monthly quantity totals ensuring sum equals fixed monthly quantity
- Handling of missed pickups (carried forward to next day)
- Month length variations and leap years
"""

from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple
import random
import calendar


class WasteQuantityCalculator:
    """
    Calculate daily waste quantities based on registered daily average.
    
    Logic:
    - Fixed monthly quantity = daily_waste_kg * number_of_days_in_month
    - Each day gets a randomized quantity within ±25% of average
    - Sum of all daily quantities must equal fixed monthly total
    - Non-uniform variation (not fixed percentage)
    - Missed pickups carried forward to next pickup day
    """
    
    def __init__(self, daily_waste_kg: float):
        """
        Initialize calculator with daily waste average.
        
        Args:
            daily_waste_kg: Average daily waste in kg (from BWG registration)
        """
        self.daily_waste_kg = float(daily_waste_kg)
        self.min_variation = -0.25  # -25%
        self.max_variation = 0.25   # +25%
    
    def _get_days_in_month(self, target_date: date) -> int:
        """
        Get number of days in the month containing target_date.
        Handles leap years automatically.
        """
        _, num_days = calendar.monthrange(target_date.year, target_date.month)
        return num_days
    
    def _get_month_boundaries(self, target_date: date) -> Tuple[date, date]:
        """
        Get first and last day of the month containing target_date.
        
        Returns:
            Tuple of (first_day, last_day)
        """
        _, last_day = calendar.monthrange(target_date.year, target_date.month)
        first_day = date(target_date.year, target_date.month, 1)
        last_day_date = date(target_date.year, target_date.month, last_day)
        return first_day, last_day_date
    
    def calculate_monthly_quantity(self, target_date: date) -> float:
        """
        Calculate fixed monthly quantity for the given date's month.
        
        Args:
            target_date: Any date in the desired month
            
        Returns:
            Total monthly quantity in kg
        """
        days_in_month = self._get_days_in_month(target_date)
        return self.daily_waste_kg * days_in_month
    
    def generate_daily_quantities(
        self, 
        start_date: date, 
        end_date: date,
        missed_dates: List[date] = None
    ) -> Dict[date, Dict]:
        """
        Generate randomized daily waste quantities for a date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            missed_dates: List of dates when pickup was missed (quantity carried forward)
            
        Returns:
            Dictionary mapping date -> {
                'quantity_kg': float,
                'variation_percent': float,
                'is_missed': bool,
                'carried_from_date': date or None
            }
        """
        if missed_dates is None:
            missed_dates = []
        
        missed_dates_set = set(missed_dates)
        
        # Calculate total quantity that must be distributed
        num_days = (end_date - start_date).days + 1
        total_monthly_qty = self.daily_waste_kg * num_days
        
        # Generate random variations for non-missed days
        current_date = start_date
        variations = {}
        
        while current_date <= end_date:
            if current_date not in missed_dates_set:
                # Non-uniform random variation between -25% and +25%
                variation = random.uniform(self.min_variation, self.max_variation)
                variations[current_date] = variation
            current_date += timedelta(days=1)
        
        # Calculate initial quantities based on variations
        daily_quantities = {}
        total_initial = 0
        
        current_date = start_date
        while current_date <= end_date:
            if current_date in missed_dates_set:
                daily_quantities[current_date] = {
                    'quantity_kg': 0.0,
                    'variation_percent': 0.0,
                    'is_missed': True,
                    'carried_from_date': None
                }
            else:
                variation = variations[current_date]
                base_quantity = self.daily_waste_kg * (1 + variation)
                daily_quantities[current_date] = {
                    'quantity_kg': base_quantity,
                    'variation_percent': round(variation * 100, 1),
                    'is_missed': False,
                    'carried_from_date': None
                }
                total_initial += base_quantity
            
            current_date += timedelta(days=1)
        
        # Adjust quantities to ensure sum equals total_monthly_qty
        if total_initial > 0:
            adjustment_factor = total_monthly_qty / total_initial
            
            current_date = start_date
            total_adjusted = 0
            
            while current_date <= end_date:
                if not daily_quantities[current_date]['is_missed']:
                    daily_quantities[current_date]['quantity_kg'] = round(
                        daily_quantities[current_date]['quantity_kg'] * adjustment_factor,
                        2
                    )
                    total_adjusted += daily_quantities[current_date]['quantity_kg']
                
                current_date += timedelta(days=1)
            
            # Handle rounding errors - adjust last day to ensure exact total
            last_adjustment_date = end_date
            while last_adjustment_date >= start_date:
                if not daily_quantities[last_adjustment_date]['is_missed']:
                    break
                last_adjustment_date -= timedelta(days=1)
            
            if last_adjustment_date >= start_date:
                remainder = round(total_monthly_qty - total_adjusted, 2)
                daily_quantities[last_adjustment_date]['quantity_kg'] = round(
                    daily_quantities[last_adjustment_date]['quantity_kg'] + remainder,
                    2
                )
        
        # Handle missed pickups - carry forward to next pickup day
        current_date = start_date
        while current_date <= end_date:
            if daily_quantities[current_date]['is_missed']:
                # Find next non-missed day
                next_date = current_date + timedelta(days=1)
                while next_date <= end_date:
                    if not daily_quantities[next_date]['is_missed']:
                        # Add missed day's quantity to next day
                        missed_qty = self.daily_waste_kg  # Add the missed day's worth
                        daily_quantities[next_date]['quantity_kg'] = round(
                            daily_quantities[next_date]['quantity_kg'] + missed_qty,
                            2
                        )
                        daily_quantities[next_date]['carried_from_date'] = current_date
                        break
                    next_date += timedelta(days=1)
            
            current_date += timedelta(days=1)
        
        return daily_quantities
    
    def generate_month_quantities(
        self,
        target_date: date,
        missed_dates: List[date] = None
    ) -> Dict[date, Dict]:
        """
        Generate quantities for entire month containing target_date.
        
        Args:
            target_date: Any date in the desired month
            missed_dates: List of dates when pickup was missed
            
        Returns:
            Dictionary mapping each day of the month to quantity data
        """
        first_day, last_day = self._get_month_boundaries(target_date)
        return self.generate_daily_quantities(first_day, last_day, missed_dates)
    
    def get_quantity_for_date(
        self,
        target_date: date,
        missed_dates: List[date] = None
    ) -> Dict:
        """
        Get quantity for a specific date.
        
        Args:
            target_date: The date to get quantity for
            missed_dates: List of dates when pickup was missed
            
        Returns:
            Dictionary with quantity_kg, variation_percent, is_missed, carried_from_date
        """
        first_day, last_day = self._get_month_boundaries(target_date)
        month_quantities = self.generate_daily_quantities(first_day, last_day, missed_dates)
        
        if target_date in month_quantities:
            return month_quantities[target_date]
        else:
            return {
                'quantity_kg': 0.0,
                'variation_percent': 0.0,
                'is_missed': True,
                'carried_from_date': None
            }
    
    def calculate_month_summary(
        self,
        target_date: date,
        missed_dates: List[date] = None
    ) -> Dict:
        """
        Get summary statistics for the month.
        
        Args:
            target_date: Any date in the desired month
            missed_dates: List of dates when pickup was missed
            
        Returns:
            Dictionary with monthly stats
        """
        monthly_data = self.generate_month_quantities(target_date, missed_dates)
        
        total_quantity = sum(d['quantity_kg'] for d in monthly_data.values())
        non_missed_days = sum(1 for d in monthly_data.values() if not d['is_missed'])
        missed_days = sum(1 for d in monthly_data.values() if d['is_missed'])
        
        variations = [d['variation_percent'] for d in monthly_data.values() if not d['is_missed']]
        
        return {
            'month': target_date.strftime('%B %Y'),
            'fixed_monthly_quantity_kg': round(self.calculate_monthly_quantity(target_date), 2),
            'actual_total_quantity_kg': round(total_quantity, 2),
            'days_in_month': len(monthly_data),
            'pickup_days': non_missed_days,
            'missed_days': missed_days,
            'average_variation_percent': round(sum(variations) / len(variations), 1) if variations else 0.0,
            'min_variation_percent': round(min(variations), 1) if variations else 0.0,
            'max_variation_percent': round(max(variations), 1) if variations else 0.0,
        }


def get_waste_calculator(daily_waste_kg: float) -> WasteQuantityCalculator:
    """Factory function to create a waste calculator instance."""
    return WasteQuantityCalculator(daily_waste_kg)
