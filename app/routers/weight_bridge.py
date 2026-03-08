# app/routers/weight_bridge.py
from fastapi import APIRouter, Body, HTTPException
from psycopg2.errors import UniqueViolation, ForeignKeyViolation

from app.database import get_db

router = APIRouter(prefix="/weight-bridge", tags=["Weight Bridge"])


@router.get("")
def list_weight_bridge_entries():
    """Return all weight bridge entries with ward context."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT wb.sl_no,
                   wb.date,
                   wb.vehicle_no,
                   wb.rate,
                   wb.time,
                   wb.material,
                   wb.ward_id,
                   w.ward_number,
                   w.ward_name,
                   wb.gross_weight,
                   wb.tare_weight,
                   wb.net_weight
            FROM weight_bridge wb
            LEFT JOIN wards w ON wb.ward_id = w.id
            ORDER BY wb.date DESC NULLS LAST, wb.sl_no DESC
            """
        )
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]


@router.post("")
def create_weight_bridge_entry(body: dict = Body(...)):
    if not body:
        raise HTTPException(status_code=400, detail="Empty payload")

    # Auto-calculate net_weight if possible
    gross_weight = body.get("gross_weight")
    tare_weight = body.get("tare_weight")
    if body.get("net_weight") is None and gross_weight is not None and tare_weight is not None:
        try:
            body["net_weight"] = float(gross_weight) - float(tare_weight)
        except (TypeError, ValueError):
            pass  # Ignore calculation if invalid

    # Never allow client to send sl_no
    body.pop("sl_no", None)

    columns = []
    values = []
    placeholders = []

    for key, value in body.items():
        columns.append(key)
        values.append(value)
        placeholders.append("%s")

    if not columns:
        raise HTTPException(status_code=400, detail="No valid fields provided")

    query = f"""
        INSERT INTO weight_bridge ({', '.join(columns)})
        VALUES ({', '.join(placeholders)})
        RETURNING *
    """

    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute(query, values)
            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

        except ForeignKeyViolation:
            raise HTTPException(status_code=400, detail="Invalid foreign key value")
        except UniqueViolation:
            raise HTTPException(status_code=400, detail="Duplicate value error")