# app/routers/wards.py
from fastapi import APIRouter, HTTPException, Query
from psycopg2.extras import RealDictCursor
from app.database import get_db

router = APIRouter(prefix="/wards", tags=["Wards"])

@router.get("/")
async def get_wards(zone_id: int = Query(None, description="Zone ID is optional")):
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT id, ward_number, ward_name 
                FROM wards 
                WHERE zone_id = %s 
                ORDER BY ward_number ASC
                """,
                (zone_id,)
            )
            rows = cur.fetchall()

        return list(rows)

    except Exception as e:
        print("Error fetching wards:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch wards")