from fastapi import APIRouter, HTTPException
from app.database import get_db
from psycopg2.extras import RealDictCursor
from app.services.waste_calculator import get_waste_calculator
from app.services.daily_analytics_service import DailyAnalyticsGenerator, BwgCollectionReportGenerator
from datetime import date
import logging
import calendar
import random

router = APIRouter(tags=["reports"])
logger = logging.getLogger("uvicorn.error")

@router.get("/full-report-data")
def get_full_report_data():
    """
    Fetch all data needed for admin analytics reports, joining vehicle_logs, vehicles, bwg, wards, and weigh_bridge_data tables.
    Returns comprehensive data for all three report types with calculated waste quantities.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT 
                    vl.log_id,
                    vl.log_date as date,
                    TO_CHAR(vl.created_at, 'HH24:MI:SS') as time,
                    v.registration_number as vehicle_no,
                    vl.corporation as gba_corporation,
                    w.ward_number,
                    w.ward_name,
                    CONCAT(w.ward_number, ' - ', w.ward_name) as ward_info,
                    wb.weigh_id,
                    wb.tare_weight,
                    wb.gross_weight,
                    wb.net_weight,
                    MAX(b.id) as bwg_id,
                    MAX(b.person) as bwg_name,
                    MAX(b.daily_waste_kg) as daily_waste_kg,
                    'segregated' as waste_type,
                    wb.net_weight as total_bulk_waste,
                    wb.net_weight * 0.60 as wet,
                    wb.net_weight * 0.40 as dry,
                    (wb.net_weight * 0.60 * 0.30) AS compost_production,
                    (wb.net_weight * 0.40 * 0.20) AS recyclables,
                    (wb.net_weight * 0.60 * 0.10) + (wb.net_weight * 0.40 * 0.65) AS rdf,
                    (wb.net_weight * 0.60 * 0.60) + (wb.net_weight * 0.40 * 0.10) AS moisture_loss,
                    (wb.net_weight * 0.60 * 0.02) + (wb.net_weight * 0.40 * 0.02) AS inerts
                FROM vehicle_logs vl
                LEFT JOIN vehicles v ON vl.vehicle_id = v.vehicle_id
                LEFT JOIN weigh_bridge_data wb ON vl.weigh_bridge_id = wb.weigh_id
                LEFT JOIN wards w ON vl.ward_id = w.id
                LEFT JOIN trips t ON vl.vehicle_id = t.vehicle_id AND vl.log_date::date = t.trip_date
                LEFT JOIN pickups p ON t.trip_id = p.trip_id
                LEFT JOIN bwg b ON p.bwg_id = b.id
                GROUP BY vl.log_id, vl.log_date, vl.created_at, v.registration_number, vl.corporation, w.ward_number, w.ward_name, wb.weigh_id, wb.tare_weight, wb.gross_weight, wb.net_weight
                ORDER BY vl.log_date DESC, vl.created_at DESC
            ''')
            rows = cur.fetchall()
            cur.close()
            
            # Enrich with calculated quantities if daily_waste_kg is available
            result = []
            for row in rows:
                row_dict = dict(row)
                
                if row_dict.get('daily_waste_kg') and row_dict.get('date'):
                    try:
                        daily_waste = float(row_dict['daily_waste_kg'])
                        date_obj = row_dict['date']

                        # Calculate the number of days in the month
                        year, month = date_obj.year, date_obj.month
                        days_in_month = calendar.monthrange(year, month)[1]

                        # Calculate the fixed monthly quantity
                        fixed_monthly_quantity = daily_waste * days_in_month

                        # Generate randomized daily quantities
                        daily_quantities = []
                        for _ in range(days_in_month):
                            variation = random.uniform(-0.25, 0.25)  # Random variation between -25% and +25%
                            daily_quantity = daily_waste * (1 + variation)
                            daily_quantities.append(daily_quantity)

                        # Adjust daily quantities to ensure the sum equals the fixed monthly quantity
                        adjustment_factor = fixed_monthly_quantity / sum(daily_quantities)
                        daily_quantities = [q * adjustment_factor for q in daily_quantities]

                        # Handle missed pickups
                        missed_days = random.sample(range(days_in_month), k=random.randint(0, days_in_month // 4))  # Random missed days
                        for day in missed_days:
                            if day + 1 < days_in_month:
                                daily_quantities[day + 1] += daily_quantities[day]  # Carry forward
                                daily_quantities[day] = 0  # Mark as missed

                        row_dict['daily_quantities'] = daily_quantities
                        row_dict['fixed_monthly_quantity'] = fixed_monthly_quantity
                    except Exception as calc_error:
                        logger.error(f"Error in waste calculation: {calc_error}")
                        pass
                
                result.append(row_dict)
            
            return result
    except Exception as e:
        logger.error(f"Error in /full-report-data endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bwg-collection-summary")
def get_bwg_collection_summary():
    """
    Get aggregated BWG collection summary grouped by corporation
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT 
                    vl.corporation,
                    COUNT(*) as total_collections,
                    COUNT(DISTINCT vl.vehicle_id) as unique_vehicles,
                    COUNT(DISTINCT vl.ward_id) as unique_wards
                FROM vehicle_logs vl
                WHERE vl.corporation IS NOT NULL
                GROUP BY vl.corporation
                ORDER BY total_collections DESC
            ''')
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bwg-quantity-analytics/{bwg_id}")
def get_bwg_quantity_analytics(bwg_id: str, year: int = None, month: int = None):
    """
    Get detailed quantity analytics for a specific BWG including:
    - Daily waste quantities with variation percentages
    - Monthly totals and summaries
    - Missed pickup tracking
    - Variation statistics
    
    Query Parameters:
    - year: Year for calculation (defaults to current year)
    - month: Month for calculation (defaults to current month)
    """
    try:
        from datetime import datetime
        
        # Default to current month if not specified
        today = date.today() if isinstance(date, type) else datetime.now().date()
        calc_year = year or today.year
        calc_month = month or today.month
        
        # Validate month
        if not (1 <= calc_month <= 12):
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
        
        with get_db() as conn:
            # Get BWG details
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT id, organization, daily_waste_kg
                FROM bwg
                WHERE id = %s
            ''', (bwg_id,))
            bwg_data = cur.fetchone()
            
            if not bwg_data:
                raise HTTPException(status_code=404, detail="BWG not found")
            
            daily_waste_kg = float(bwg_data['daily_waste_kg']) if bwg_data['daily_waste_kg'] else 0
            
            # Get pickup data for the month
            cur.execute('''
                SELECT 
                    p.pickup_id,
                    p.scheduled_date,
                    p.status,
                    p.quantity_kg,
                    p.variation_percent,
                    p.is_missed,
                    p.carried_from_date
                FROM pickups p
                WHERE p.bwg_id = %s
                  AND EXTRACT(YEAR FROM p.scheduled_date) = %s
                  AND EXTRACT(MONTH FROM p.scheduled_date) = %s
                ORDER BY p.scheduled_date ASC
            ''', (bwg_id, calc_year, calc_month))
            
            pickup_records = cur.fetchall()
            cur.close()
            
            # If we have pickup data, use it; otherwise calculate
            if pickup_records:
                # Use actual pickup data from database
                daily_data = {}
                total_quantity = 0
                missed_days = 0
                
                for record in pickup_records:
                    daily_data[record['scheduled_date']] = {
                        'pickup_id': record['pickup_id'],
                        'quantity_kg': float(record['quantity_kg'] or 0),
                        'variation_percent': float(record['variation_percent'] or 0),
                        'is_missed': record['is_missed'] or False,
                        'carried_from_date': record['carried_from_date'],
                        'status': record['status']
                    }
                    total_quantity += float(record['quantity_kg'] or 0)
                    if record['is_missed']:
                        missed_days += 1
            else:
                # Generate calculated data based on daily_waste_kg
                if daily_waste_kg <= 0:
                    raise HTTPException(status_code=400, detail="BWG has no daily waste quantity set")
                
                calculator = get_waste_calculator(daily_waste_kg)
                target_date = date(calc_year, calc_month, 1)
                
                # Get any missed dates from database
                cur = conn.cursor()
                cur.execute('''
                    SELECT DISTINCT scheduled_date
                    FROM pickups
                    WHERE bwg_id = %s
                      AND is_missed = true
                      AND EXTRACT(YEAR FROM scheduled_date) = %s
                      AND EXTRACT(MONTH FROM scheduled_date) = %s
                ''', (bwg_id, calc_year, calc_month))
                missed_dates_records = cur.fetchall()
                cur.close()
                missed_dates = [row[0] for row in missed_dates_records]
                
                calculated_quantities = calculator.generate_month_quantities(target_date, missed_dates)
                
                daily_data = {}
                total_quantity = 0
                missed_days = 0
                
                for calc_date, qty_data in calculated_quantities.items():
                    daily_data[calc_date] = {
                        'quantity_kg': qty_data['quantity_kg'],
                        'variation_percent': qty_data['variation_percent'],
                        'is_missed': qty_data['is_missed'],
                        'carried_from_date': qty_data['carried_from_date'],
                        'status': 'CALCULATED'
                    }
                    total_quantity += qty_data['quantity_kg']
                    if qty_data['is_missed']:
                        missed_days += 1
            
            # Prepare summary
            import calendar
            _, days_in_month = calendar.monthrange(calc_year, calc_month)
            fixed_monthly_qty = daily_waste_kg * days_in_month
            
            summary = {
                'bwg_id': bwg_id,
                'bwg_name': bwg_data['organization'],
                'daily_waste_kg': daily_waste_kg,
                'year': calc_year,
                'month': calc_month,
                'month_name': date(calc_year, calc_month, 1).strftime('%B %Y'),
                'days_in_month': days_in_month,
                'fixed_monthly_quantity_kg': round(fixed_monthly_qty, 2),
                'actual_total_quantity_kg': round(total_quantity, 2),
                'pickup_days': days_in_month - missed_days,
                'missed_days': missed_days,
                'daily_breakdown': daily_data
            }
            
            return summary
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/waste-processing-summary")
def get_waste_processing_summary():
    """
    Get aggregated waste processing summary by date
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT 
                    wb.weigh_date as date,
                    SUM(wb.net_weight) as total_bulk_waste,
                    SUM(wb.net_weight * 0.60) as wet,
                    SUM(wb.net_weight * 0.40) as dry,
                    (wb.net_weight * 0.60 * 0.30) AS compost_production,
                    (wb.net_weight * 0.40 * 0.20) AS recyclables, -- Updated to 20% of dry waste
                    (wb.net_weight * 0.60 * 0.10) + (wb.net_weight * 0.40 * 0.65) AS rdf,
                    (wb.net_weight * 0.60 * 0.60) + (wb.net_weight * 0.40 * 0.10) AS moisture_loss,
                    (wb.net_weight * 0.60 * 0.02) + (wb.net_weight * 0.40 * 0.02) AS inerts,
                    COUNT(*) as total_records
                FROM weigh_bridge_data wb
                WHERE wb.net_weight IS NOT NULL
                GROUP BY wb.weigh_date
                ORDER BY wb.weigh_date DESC
            ''')
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vehicle-weighbridge-reports")
def get_vehicle_weighbridge_reports():
    """
    Fetch Vehicle Wise Weighbridge Logs Reports directly from the weight_bridge table.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT 
                    sl_no AS weigh_id,
                    date AS weigh_date,
                    time,
                    vehicle_no AS vehicle_number,
                    gross_weight AS tare_wt,
                    tare_weight AS gross_wt,
                    net_weight AS net_wt,
                    ward_name,
                    CONCAT(ward_number, ' - ', ward_name) AS ward_info,
                    zone_name AS gba_corporation
                FROM weight_bridge
                ORDER BY date DESC, time DESC
                LIMIT 100
            """)

            data = cur.fetchall()
            cur.close()
            return data

    except Exception as e:
        logger.error(f"Error fetching vehicle weighbridge reports: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/daily-analytics/bwg-wise/{bwg_id}")
def get_bwg_wise_daily_analytics(bwg_id: str, from_date: str = None, to_date: str = None):
    """
    Get daily BWG wise analytics with random variations within ±25% range.
    Includes variation percentages and calculated quantities.
    
    Query Parameters:
    - from_date: Start date (ISO format, defaults to 30 days ago)
    - to_date: End date (ISO format, defaults to today)
    """
    try:
        from datetime import datetime, timedelta
        
        # Default date range - last 30 days
        to_dt = datetime.fromisoformat(to_date) if to_date else datetime.now()
        to_date_val = to_dt.date()
        
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
            from_date_val = from_dt.date()
        else:
            from_date_val = to_date_val - timedelta(days=29)
        
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT 
                    date,
                    bwg_wise_variation_percent as variation_percent,
                    bwg_wise_quantity_kg as calculated_quantity_kg,
                    created_at
                FROM daily_processing_analytics
                WHERE bwg_id = %s
                  AND date BETWEEN %s AND %s
                ORDER BY date DESC
            ''', (bwg_id, from_date_val, to_date_val))
            
            rows = cur.fetchall()
            cur.close()
            
            return {
                "bwg_id": bwg_id,
                "period": f"{from_date_val} to {to_date_val}",
                "count": len(rows),
                "analytics": [dict(row) for row in rows]
            }
    
    except Exception as e:
        logger.error(f"Error fetching BWG wise analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-analytics/vehicle-wise/{vehicle_id}")
def get_vehicle_wise_daily_analytics(vehicle_id: int, from_date: str = None, to_date: str = None):
    """
    Get daily vehicle wise analytics with random variations within ±25% range.
    Includes variation percentages and calculated quantities.
    
    Query Parameters:
    - from_date: Start date (ISO format, defaults to 30 days ago)
    - to_date: End date (ISO format, defaults to today)
    """
    try:
        from datetime import datetime, timedelta
        
        # Default date range - last 30 days
        to_dt = datetime.fromisoformat(to_date) if to_date else datetime.now()
        to_date_val = to_dt.date()
        
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
            from_date_val = from_dt.date()
        else:
            from_date_val = to_date_val - timedelta(days=29)
        
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT 
                    date,
                    vehicle_wise_variation_percent as variation_percent,
                    vehicle_wise_quantity_kg as calculated_quantity_kg,
                    created_at
                FROM daily_processing_analytics
                WHERE vehicle_id = %s
                  AND date BETWEEN %s AND %s
                ORDER BY date DESC
            ''', (vehicle_id, from_date_val, to_date_val))
            
            rows = cur.fetchall()
            cur.close()
            
            return {
                "vehicle_id": vehicle_id,
                "period": f"{from_date_val} to {to_date_val}",
                "count": len(rows),
                "analytics": [dict(row) for row in rows]
            }
    
    except Exception as e:
        logger.error(f"Error fetching vehicle wise analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-analytics/total-processing")
def get_total_processing_daily_analytics(from_date: str = None, to_date: str = None):
    """
    Get daily total processing analytics with random variations within ±25% range.
    Includes variation percentages and calculated quantities for all processing combined.
    
    Query Parameters:
    - from_date: Start date (ISO format, defaults to 30 days ago)
    - to_date: End date (ISO format, defaults to today)
    """
    try:
        from datetime import datetime, timedelta
        
        # Default date range - last 30 days
        to_dt = datetime.fromisoformat(to_date) if to_date else datetime.now()
        to_date_val = to_dt.date()
        
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
            from_date_val = from_dt.date()
        else:
            from_date_val = to_date_val - timedelta(days=29)
        
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT 
                    date,
                    total_processing_variation_percent as variation_percent,
                    total_processing_quantity_kg as calculated_quantity_kg,
                    created_at
                FROM daily_processing_analytics
                WHERE bwg_id IS NULL
                  AND vehicle_id IS NULL
                  AND date BETWEEN %s AND %s
                ORDER BY date DESC
            ''', (from_date_val, to_date_val))
            
            rows = cur.fetchall()
            cur.close()
            
            return {
                "type": "total_processing",
                "period": f"{from_date_val} to {to_date_val}",
                "count": len(rows),
                "analytics": [dict(row) for row in rows]
            }
    
    except Exception as e:
        logger.error(f"Error fetching total processing analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daily-analytics/regenerate")
def regenerate_daily_analytics(target_date: str = None):
    """
    Manually trigger daily analytics regeneration.
    Regenerates random variations for all BWGs, vehicles, and total processing.
    
    Query Parameters:
    - target_date: Date to regenerate (ISO format, defaults to today)
    
    Returns:
        Dictionary with counts of regenerated records
    """
    try:
        from datetime import datetime
        
        target_dt = None
        if target_date:
            target_dt = datetime.fromisoformat(target_date).date()
        
        stats = DailyAnalyticsGenerator.regenerate_daily_analytics(target_dt)
        
        return {
            "success": True,
            "target_date": target_dt or date.today(),
            "generated": stats
        }
    
    except Exception as e:
        logger.error(f"Error regenerating analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bwg-collection-reports")
def get_bwg_collection_reports(from_date: str = None, to_date: str = None, bwg_id: int = None):
    """
    Fetch BWG collection reports with optional filtering.
    
    Query Parameters:
    - from_date: Start date (ISO format, defaults to 30 days ago)
    - to_date: End date (ISO format, defaults to today)
    - bwg_id: Filter by specific BWG ID (optional)
    
    Returns:
        List of collection reports with waste quantities
    """
    try:
        from datetime import datetime, timedelta
        
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Parse dates
            to_dt = datetime.fromisoformat(to_date).date() if to_date else date.today()
            from_dt = datetime.fromisoformat(from_date).date() if from_date else (to_dt - timedelta(days=30))
            
            # Build query
            query = '''
                SELECT 
                    id,
                    bwg_id,
                    bwg_name,
                    date,
                    corporation,
                    ward_info,
                    wet_waste_kg,
                    dry_waste_kg,
                    (wet_waste_kg + dry_waste_kg) as total_waste_kg,
                    vehicle_no,
                    created_at,
                    updated_at
                FROM bwg_collection_report
                WHERE date BETWEEN %s AND %s
            '''
            params = [from_dt, to_dt]
            
            if bwg_id:
                query += ' AND bwg_id = %s'
                params.append(bwg_id)
            
            query += ' ORDER BY date DESC, bwg_id ASC'
            
            cur.execute(query, params)
            rows = cur.fetchall()
            
            return {
                "from_date": from_dt,
                "to_date": to_dt,
                "total_records": len(rows),
                "reports": [dict(row) for row in rows]
            }
    
    except Exception as e:
        logger.error(f"Error fetching BWG collection reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bwg-collection-reports/{bwg_id}")
def get_bwg_collection_reports_by_id(bwg_id: int, from_date: str = None, to_date: str = None):
    """
    Fetch collection reports for a specific BWG.
    
    Path Parameters:
    - bwg_id: The BWG ID to fetch reports for
    
    Query Parameters:
    - from_date: Start date (ISO format, defaults to 30 days ago)
    - to_date: End date (ISO format, defaults to today)
    
    Returns:
        List of collection reports for the specified BWG
    """
    try:
        from datetime import datetime, timedelta
        
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Parse dates
            to_dt = datetime.fromisoformat(to_date).date() if to_date else date.today()
            from_dt = datetime.fromisoformat(from_date).date() if from_date else (to_dt - timedelta(days=30))
            
            query = '''
                SELECT 
                    id,
                    bwg_id,
                    bwg_name,
                    date,
                    corporation,
                    ward_info,
                    wet_waste_kg,
                    dry_waste_kg,
                    (wet_waste_kg + dry_waste_kg) as total_waste_kg,
                    vehicle_no,
                    created_at,
                    updated_at
                FROM bwg_collection_report
                WHERE bwg_id = %s AND date BETWEEN %s AND %s
                ORDER BY date DESC
            '''
            
            cur.execute(query, [bwg_id, from_dt, to_dt])
            rows = cur.fetchall()
            
            if not rows:
                return {
                    "bwg_id": bwg_id,
                    "from_date": from_dt,
                    "to_date": to_dt,
                    "total_records": 0,
                    "reports": []
                }
            
            return {
                "bwg_id": bwg_id,
                "bwg_name": rows[0]['bwg_name'],
                "corporation": rows[0]['corporation'],
                "ward_info": rows[0]['ward_info'],
                "from_date": from_dt,
                "to_date": to_dt,
                "total_records": len(rows),
                "reports": [dict(row) for row in rows]
            }
    
    except Exception as e:
        logger.error(f"Error fetching collection reports for BWG {bwg_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bwg-collection-reports/regenerate")
def regenerate_bwg_collection_reports(target_date: str = None):
    """
    Manually trigger BWG collection report regeneration.
    Regenerates reports for all approved BWGs with ±25% waste variations.
    
    Query Parameters:
    - target_date: Date to regenerate (ISO format, defaults to today)
    
    Returns:
        Dictionary with counts of created and updated records
    """
    try:
        from datetime import datetime
        from app.services.daily_analytics_service import BwgCollectionReportGenerator
        
        target_dt = None
        if target_date:
            target_dt = datetime.fromisoformat(target_date).date()
        
        stats = BwgCollectionReportGenerator.generate_collection_reports_for_date(target_dt)
        
        return {
            "success": True,
            "target_date": target_dt or date.today(),
            "created": stats.get('created', 0),
            "updated": stats.get('updated', 0),
            "total": stats.get('created', 0) + stats.get('updated', 0)
        }
    
    except Exception as e:
        logger.error(f"Error regenerating BWG collection reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bwg-collection-reports/daily-summary/{date}")
def get_daily_bwg_summary(date: str):
    """
    Fetch a summary of all BWG collection reports for a specific date.
    
    Path Parameters:
    - date: Date to fetch summary for (ISO format)
    
    Returns:
        Summary with total waste, BWG count, and detailed records
    """
    try:
        from datetime import datetime
        
        target_date = datetime.fromisoformat(date).date()
        
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = '''
                SELECT 
                    id,
                    bwg_id,
                    bwg_name,
                    corporation,
                    ward_info,
                    wet_waste_kg,
                    dry_waste_kg,
                    (wet_waste_kg + dry_waste_kg) as total_waste_kg
                FROM bwg_collection_report
                WHERE date = %s
                ORDER BY bwg_id ASC
            '''
            
            cur.execute(query, [target_date])
            rows = cur.fetchall()
            
            if not rows:
                return {
                    "date": target_date,
                    "bwg_count": 0,
                    "total_wet_waste": 0,
                    "total_dry_waste": 0,
                    "total_waste": 0,
                    "reports": []
                }
            
            total_wet = sum(float(row['wet_waste_kg'] or 0) for row in rows)
            total_dry = sum(float(row['dry_waste_kg'] or 0) for row in rows)
            
            return {
                "date": target_date,
                "bwg_count": len(rows),
                "total_wet_waste": round(total_wet, 2),
                "total_dry_waste": round(total_dry, 2),
                "total_waste": round(total_wet + total_dry, 2),
                "reports": [dict(row) for row in rows]
            }
    
    except Exception as e:
        logger.error(f"Error fetching daily summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
