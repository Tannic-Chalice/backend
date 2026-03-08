from fastapi import APIRouter, HTTPException
from app.database import get_db
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/metrics")
def admin_metrics(period: str = "daily", from_: str = None, to: str = None):
    """
    Fetch aggregated metrics for all BWGs.
    Query Parameters:
    - period: daily, weekly, monthly, yearly
    - from_: Start date (optional)
    - to: End date (optional)
    """
    to_date = to or datetime.utcnow().date().isoformat()
    from_date = from_

    if not from_date:
        d = datetime.fromisoformat(to_date)
        if period == "daily":
            d -= timedelta(days=29)
        elif period == "weekly":
            d -= timedelta(weeks=11)
        elif period == "monthly":
            d = d.replace(month=max(1, d.month - 11))
        elif period == "yearly":
            d = d.replace(year=d.year - 4)
        from_date = d.date().isoformat()

    trunc = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
        "yearly": "year",
    }.get(period, "day")

    query = f"""
        SELECT date_trunc('{trunc}', date) AS period_start,
               SUM(collected_kg)::numeric(12,2) AS collected,
               SUM(transported_kg)::numeric(12,2) AS transported,
               SUM(processed_kg)::numeric(12,2) AS processed,
               SUM(disposed_kg)::numeric(12,2) AS disposed
        FROM bwg_daily_aggregates
        WHERE date BETWEEN %s AND %s
        GROUP BY period_start
        ORDER BY period_start
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, (from_date, to_date))
        rows = cur.fetchall()

    labels = [row[0].date().isoformat() for row in rows]
    collected = [float(row[1] or 0) for row in rows]
    transported = [float(row[2] or 0) for row in rows]
    processed = [float(row[3] or 0) for row in rows]
    disposed = [float(row[4] or 0) for row in rows]

    return {
        "period": period,
        "labels": labels,
        "series": {
            "collected": collected,
            "transported": transported,
            "processed": processed,
            "disposed": disposed,
        },
    }


@router.get("/waste-quantity-metrics")
def waste_quantity_metrics(period: str = "daily", from_: str = None, to: str = None):
    """
    Fetch aggregated waste quantity metrics by pickup date.
    Includes both actual pickup quantities and expected quantities based on registrations.
    
    Query Parameters:
    - period: daily, weekly, monthly, yearly
    - from_: Start date (optional)
    - to: End date (optional)
    """
    from app.services.waste_calculator import get_waste_calculator
    from datetime import date
    
    to_date = to or datetime.utcnow().date().isoformat()
    from_date = from_

    if not from_date:
        d = datetime.fromisoformat(to_date)
        if period == "daily":
            d -= timedelta(days=29)
        elif period == "weekly":
            d -= timedelta(weeks=11)
        elif period == "monthly":
            d = d.replace(month=max(1, d.month - 11))
        elif period == "yearly":
            d = d.replace(year=d.year - 4)
        from_date = d.date().isoformat()

    trunc = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
        "yearly": "year",
    }.get(period, "day")

    try:
        with get_db() as conn:
            cur = conn.cursor()
            
            # Get pickup quantities (actual registered waste)
            query = f"""
                SELECT date_trunc('{trunc}', p.scheduled_date) AS period_start,
                       COUNT(*) AS pickup_count,
                       SUM(COALESCE(p.quantity_kg, 0))::numeric(12,2) AS actual_quantity_kg,
                       SUM(CASE WHEN p.is_missed = false THEN 1 ELSE 0 END) AS successful_pickups,
                       SUM(CASE WHEN p.is_missed = true THEN 1 ELSE 0 END) AS missed_pickups,
                       AVG(COALESCE(p.variation_percent, 0))::numeric(5,1) AS avg_variation_percent
                FROM pickups p
                WHERE p.scheduled_date BETWEEN %s AND %s
                GROUP BY period_start
                ORDER BY period_start
            """
            
            cur.execute(query, (from_date, to_date))
            actual_rows = cur.fetchall()
            
            # Get expected quantities based on registered daily waste
            expected_query = f"""
                SELECT date_trunc('{trunc}', p.scheduled_date) AS period_start,
                       SUM(COALESCE(b.daily_waste_kg, 0) * (SELECT COUNT(DISTINCT scheduled_date) 
                                                               FROM pickups 
                                                               WHERE bwg_id = b.id 
                                                               AND date_trunc('{trunc}', scheduled_date) = date_trunc('{trunc}', p.scheduled_date)))::numeric(12,2) AS expected_quantity_kg
                FROM pickups p
                LEFT JOIN bwg b ON p.bwg_id = b.id
                WHERE p.scheduled_date BETWEEN %s AND %s
                GROUP BY period_start
                ORDER BY period_start
            """
            
            cur.execute(expected_query, (from_date, to_date))
            expected_rows = cur.fetchall()
            cur.close()
            
            # Combine results
            metrics_map = {}
            
            for row in actual_rows:
                period_start = row[0].date().isoformat() if row[0] else None
                if period_start:
                    metrics_map[period_start] = {
                        'period': period_start,
                        'pickup_count': row[1] or 0,
                        'actual_quantity_kg': float(row[2] or 0),
                        'successful_pickups': row[3] or 0,
                        'missed_pickups': row[4] or 0,
                        'avg_variation_percent': float(row[5] or 0),
                        'expected_quantity_kg': 0,
                        'variance_kg': 0,
                        'variance_percent': 0
                    }
            
            for row in expected_rows:
                period_start = row[0].date().isoformat() if row[0] else None
                if period_start:
                    if period_start not in metrics_map:
                        metrics_map[period_start] = {
                            'period': period_start,
                            'pickup_count': 0,
                            'actual_quantity_kg': 0,
                            'successful_pickups': 0,
                            'missed_pickups': 0,
                            'avg_variation_percent': 0,
                            'expected_quantity_kg': float(row[1] or 0),
                            'variance_kg': float(row[1] or 0),
                            'variance_percent': 100
                        }
                    else:
                        metrics_map[period_start]['expected_quantity_kg'] = float(row[1] or 0)
                        actual = metrics_map[period_start]['actual_quantity_kg']
                        expected = float(row[1] or 0)
                        variance = actual - expected
                        variance_pct = (variance / expected * 100) if expected > 0 else 0
                        metrics_map[period_start]['variance_kg'] = round(variance, 2)
                        metrics_map[period_start]['variance_percent'] = round(variance_pct, 1)
            
            return {
                "period": period,
                "data": sorted(list(metrics_map.values()), key=lambda x: x['period'])
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))