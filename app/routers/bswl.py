from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from app.database import get_db

router = APIRouter(tags=["BSWML"])


def parse_date(input_str: Optional[str]) -> Optional[str]:
    if not input_str:
        return None
    try:
        d = datetime.fromisoformat(input_str[:10])
        return d.date().isoformat()
    except ValueError:
        return None


# -------------------------------------------------
# 1) GET /bswml/waste-summary
# -------------------------------------------------
@router.get("/waste-summary")
def waste_summary() -> List[Dict[str, Any]]:
    try:
        query = """
            SELECT 
                b.id,
                b.organization,
                b.waste_types,
                b.daily_waste_kg,
                b.wet_waste_kg,
                b.dry_waste_kg,
                b.price_per_kg,

                w.ward_number,
                w.ward_name,
                w.zone_name AS corporation

            FROM bwg b
            LEFT JOIN wards w ON b.ward_id = w.id
            WHERE b.status = 'approved'
            ORDER BY b.id
            LIMIT 1000
        """

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]

        return [dict(zip(cols, r)) for r in rows]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")



# -------------------------------------------------
# 2) GET /bswml/metrics
#    Query params: bwg_id, period, from, to
# -------------------------------------------------
@router.get("/metrics")
def metrics(
    bwg_id: str = Query(...),
    period: Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None, alias="to"),
):
    if not bwg_id:
        raise HTTPException(status_code=400, detail="bwg_id is required")

    to_date = parse_date(to) or datetime.utcnow().date().isoformat()
    from_date = parse_date(from_)

    with get_db() as conn:
        cur = conn.cursor()

        # -------- DAILY (default) --------
        if not period or period == "daily":
            if not from_date:
                d = datetime.fromisoformat(to_date) - timedelta(days=29)
                from_date = d.date().isoformat()

            q = """
                SELECT date, collected_kg, transported_kg, processed_kg, disposed_kg
                FROM bwg_daily_aggregates
                WHERE bwg_id = %s AND date BETWEEN %s AND %s
                ORDER BY date
            """
            cur.execute(q, (bwg_id, from_date, to_date))
            rows = cur.fetchall()

            labels = [r[0].isoformat() for r in rows]
            collected = [float(r[1] or 0) for r in rows]
            transported = [float(r[2] or 0) for r in rows]
            processed = [float(r[3] or 0) for r in rows]
            disposed = [float(r[4] or 0) for r in rows]

            return {
                "bwg_id": bwg_id,
                "period": "daily",
                "labels": labels,
                "series": {
                    "collected": collected,
                    "transported": transported,
                    "processed": processed,
                    "disposed": disposed,
                },
            }

        # -------- WEEKLY / MONTHLY / YEARLY --------
        valid_periods = ["weekly", "monthly", "yearly"]
        if period not in valid_periods:
            raise HTTPException(status_code=400, detail="invalid period")

        if not from_date:
            d = datetime.fromisoformat(to_date)
            if period == "weekly":
                d -= timedelta(days=7 * 11)
            elif period == "monthly":
                month = d.month - 11
                year = d.year
                while month <= 0:
                    month += 12
                    year -= 1
                d = d.replace(year=year, month=month)
            else:  # yearly
                d = d.replace(year=d.year - 4)
            from_date = d.date().isoformat()

        trunc = "week" if period == "weekly" else "month" if period == "monthly" else "year"

        q_agg = f"""
            SELECT date_trunc('{trunc}', date) AS period_start,
                   SUM(collected_kg)::numeric(12,2) AS collected_kg,
                   SUM(transported_kg)::numeric(12,2) AS transported_kg,
                   SUM(processed_kg)::numeric(12,2) AS processed_kg,
                   SUM(disposed_kg)::numeric(12,2) AS disposed_kg
            FROM bwg_daily_aggregates
            WHERE bwg_id = %s AND date BETWEEN %s AND %s
            GROUP BY period_start
            ORDER BY period_start
        """
        cur.execute(q_agg, (bwg_id, from_date, to_date))
        rows = cur.fetchall()

        labels = [r[0].date().isoformat() for r in rows]
        collected = [float(r[1] or 0) for r in rows]
        transported = [float(r[2] or 0) for r in rows]
        processed = [float(r[3] or 0) for r in rows]
        disposed = [float(r[4] or 0) for r in rows]

        return {
            "bwg_id": bwg_id,
            "period": period,
            "labels": labels,
            "series": {
                "collected": collected,
                "transported": transported,
                "processed": processed,
                "disposed": disposed,
            },
        }


# -------------------------------------------------
# 3) GET /bswml/bwgs
# -------------------------------------------------
@router.get("/bwgs")
def bwgs_list():
    query = "SELECT DISTINCT bwg_id FROM bwg_daily_aggregates ORDER BY bwg_id"

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()

    return [{"id": str(r[0]), "label": str(r[0])} for r in rows]
