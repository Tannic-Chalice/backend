"""
Utility functions for integrating waste quantity calculations with pickup operations

Provides helpers for:
- Calculating quantities when creating/updating pickups
- Bulk updating quantities for a month
- Handling missed pickup cascades
"""

from datetime import date, datetime
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from app.database import get_db
from app.services.waste_calculator import get_waste_calculator


def get_bwg_daily_waste(bwg_id: str) -> Optional[float]:
    """
    Retrieve the daily waste kg for a BWG from the database.
    
    Args:
        bwg_id: BWG identifier
        
    Returns:
        Daily waste in kg, or None if not found
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT daily_waste_kg FROM bwg WHERE id = %s", (bwg_id,))
            result = cur.fetchone()
            cur.close()
            
            if result and result[0]:
                return float(result[0])
    except Exception as e:
        print(f"Error retrieving daily waste for BWG {bwg_id}: {str(e)}")
    
    return None


def calculate_and_update_pickup_quantity(
    bwg_id: str,
    pickup_date: date,
    missed_dates: Optional[List[date]] = None
) -> Dict:
    """
    Calculate the waste quantity for a specific pickup and return the data.
    
    Args:
        bwg_id: BWG identifier
        pickup_date: Date of the pickup
        missed_dates: List of previously missed pickup dates in the same month
        
    Returns:
        Dictionary with calculated quantity data {
            'quantity_kg': float,
            'variation_percent': float,
            'is_missed': bool,
            'carried_from_date': date or None
        }
    """
    daily_waste = get_bwg_daily_waste(bwg_id)
    if not daily_waste:
        return {
            'quantity_kg': 0.0,
            'variation_percent': 0.0,
            'is_missed': True,
            'carried_from_date': None
        }
    
    calculator = get_waste_calculator(daily_waste)
    return calculator.get_quantity_for_date(pickup_date, missed_dates)


def update_monthly_quantities(
    bwg_id: str,
    year: int,
    month: int
) -> Dict:
    """
    Calculate and update all pickup quantities for a given month.
    
    This function:
    1. Gets all pickups for the month
    2. Calculates quantities based on daily waste
    3. Updates pickup records in database
    4. Returns summary of updates
    
    Args:
        bwg_id: BWG identifier
        year: Year for the month
        month: Month (1-12)
        
    Returns:
        Summary dictionary with update count and results
    """
    daily_waste = get_bwg_daily_waste(bwg_id)
    if not daily_waste:
        return {
            'success': False,
            'message': 'BWG has no daily waste quantity registered',
            'updated_count': 0
        }
    
    # Get all pickups for the month
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT pickup_id, scheduled_date, is_missed
                FROM pickups
                WHERE bwg_id = %s
                  AND EXTRACT(YEAR FROM scheduled_date) = %s
                  AND EXTRACT(MONTH FROM scheduled_date) = %s
                ORDER BY scheduled_date ASC
            """, (bwg_id, year, month))
            
            pickups = cur.fetchall()
            cur.close()
            
            if not pickups:
                return {
                    'success': True,
                    'message': 'No pickups found for the period',
                    'updated_count': 0
                }
            
            # Get missed dates
            missed_dates = [p[1] for p in pickups if p[2]]  # p[2] is is_missed
            
            # Calculate quantities for entire month
            calculator = get_waste_calculator(daily_waste)
            target_date = date(year, month, 1)
            month_quantities = calculator.generate_month_quantities(target_date, missed_dates)
            
            # Update each pickup
            updated_count = 0
            with get_db() as conn:
                cur = conn.cursor()
                
                for pickup_id, scheduled_date, is_missed in pickups:
                    if scheduled_date in month_quantities:
                        qty_data = month_quantities[scheduled_date]
                        
                        cur.execute("""
                            UPDATE pickups
                            SET quantity_kg = %s,
                                variation_percent = %s,
                                is_missed = %s,
                                carried_from_date = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE pickup_id = %s
                        """, (
                            qty_data['quantity_kg'],
                            qty_data['variation_percent'],
                            qty_data['is_missed'],
                            qty_data['carried_from_date'],
                            pickup_id
                        ))
                        updated_count += 1
                
                conn.commit()
            
            return {
                'success': True,
                'message': f'Successfully updated {updated_count} pickups',
                'updated_count': updated_count,
                'month': f"{year}-{month:02d}"
            }
            
    except Exception as e:
        return {
            'success': False,
            'message': f'Error updating quantities: {str(e)}',
            'updated_count': 0
        }


def handle_missed_pickup(
    bwg_id: str,
    missed_date: date
) -> Dict:
    """
    Mark a pickup as missed and cascade the quantity to the next pickup.
    
    Args:
        bwg_id: BWG identifier
        missed_date: Date of the missed pickup
        
    Returns:
        Dictionary with operation results
    """
    try:
        daily_waste = get_bwg_daily_waste(bwg_id)
        if not daily_waste:
            return {
                'success': False,
                'message': 'BWG has no daily waste quantity registered'
            }
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Find the missed pickup
            cur.execute("""
                SELECT pickup_id FROM pickups
                WHERE bwg_id = %s AND scheduled_date = %s
            """, (bwg_id, missed_date))
            
            missed_pickup = cur.fetchone()
            if not missed_pickup:
                cur.close()
                return {
                    'success': False,
                    'message': f'No pickup found for {bwg_id} on {missed_date}'
                }
            
            missed_pickup_id = missed_pickup[0]
            
            # Find next pickup date
            cur.execute("""
                SELECT pickup_id, scheduled_date FROM pickups
                WHERE bwg_id = %s AND scheduled_date > %s
                ORDER BY scheduled_date ASC
                LIMIT 1
            """, (bwg_id, missed_date))
            
            next_pickup = cur.fetchone()
            if not next_pickup:
                cur.close()
                return {
                    'success': False,
                    'message': f'No subsequent pickup found after {missed_date}'
                }
            
            next_pickup_id, next_pickup_date = next_pickup
            
            # Mark current as missed
            cur.execute("""
                UPDATE pickups
                SET is_missed = true,
                    quantity_kg = 0,
                    variation_percent = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE pickup_id = %s
            """, (missed_pickup_id,))
            
            # Update next pickup to carry forward this day's quantity
            next_qty = daily_waste * 1.2  # Some variation (for example)
            cur.execute("""
                UPDATE pickups
                SET carried_from_date = %s,
                    quantity_kg = quantity_kg + %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE pickup_id = %s
            """, (missed_date, daily_waste, next_pickup_id))
            
            conn.commit()
            cur.close()
            
            return {
                'success': True,
                'message': f'Marked pickup on {missed_date} as missed and carried forward to {next_pickup_date}',
                'missed_pickup_id': missed_pickup_id,
                'next_pickup_id': next_pickup_id,
                'next_pickup_date': str(next_pickup_date),
                'carried_quantity_kg': daily_waste
            }
            
    except Exception as e:
        return {
            'success': False,
            'message': f'Error handling missed pickup: {str(e)}'
        }


def get_month_pickup_status(bwg_id: str, year: int, month: int) -> Dict:
    """
    Get comprehensive pickup and quantity status for a month.
    
    Args:
        bwg_id: BWG identifier
        year: Year
        month: Month (1-12)
        
    Returns:
        Dictionary with month status including all pickups and quantities
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()
            
            # Get BWG info
            cur.execute("""
                SELECT organization, daily_waste_kg FROM bwg WHERE id = %s
            """, (bwg_id,))
            bwg_info = cur.fetchone()
            
            if not bwg_info:
                cur.close()
                return {'success': False, 'message': 'BWG not found'}
            
            org_name, daily_waste = bwg_info
            
            # Get all pickups for the month
            cur.execute("""
                SELECT 
                    pickup_id, scheduled_date, status,
                    quantity_kg, variation_percent, is_missed, carried_from_date
                FROM pickups
                WHERE bwg_id = %s
                  AND EXTRACT(YEAR FROM scheduled_date) = %s
                  AND EXTRACT(MONTH FROM scheduled_date) = %s
                ORDER BY scheduled_date ASC
            """, (bwg_id, year, month))
            
            pickups = cur.fetchall()
            cur.close()
            
            if not pickups:
                return {
                    'success': True,
                    'bwg_id': bwg_id,
                    'organization': org_name,
                    'month': f"{year}-{month:02d}",
                    'daily_waste_kg': float(daily_waste) if daily_waste else 0,
                    'message': 'No pickups found for this month',
                    'pickups': []
                }
            
            # Build response
            pickup_list = []
            total_quantity = 0
            successful_count = 0
            missed_count = 0
            
            for p in pickups:
                pickup_id, sched_date, status, qty, var, is_missed, carried_from = p
                
                pickup_data = {
                    'pickup_id': pickup_id,
                    'scheduled_date': str(sched_date),
                    'status': status,
                    'quantity_kg': float(qty) if qty else 0,
                    'variation_percent': float(var) if var else 0,
                    'is_missed': is_missed or False,
                    'carried_from_date': str(carried_from) if carried_from else None
                }
                
                pickup_list.append(pickup_data)
                total_quantity += float(qty) if qty else 0
                
                if is_missed:
                    missed_count += 1
                else:
                    successful_count += 1
            
            import calendar
            _, days_in_month = calendar.monthrange(year, month)
            fixed_monthly = (float(daily_waste) if daily_waste else 0) * days_in_month
            
            return {
                'success': True,
                'bwg_id': bwg_id,
                'organization': org_name,
                'month': f"{year}-{month:02d}",
                'daily_waste_kg': float(daily_waste) if daily_waste else 0,
                'days_in_month': days_in_month,
                'fixed_monthly_quantity_kg': round(fixed_monthly, 2),
                'actual_total_quantity_kg': round(total_quantity, 2),
                'successful_pickups': successful_count,
                'missed_pickups': missed_count,
                'total_pickups': len(pickup_list),
                'pickups': pickup_list
            }
            
    except Exception as e:
        return {
            'success': False,
            'message': f'Error retrieving month status: {str(e)}'
        }
