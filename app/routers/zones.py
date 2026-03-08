# app/routers/zones.py
from fastapi import APIRouter, HTTPException
from app.database import get_db
from psycopg2.extras import RealDictCursor

router = APIRouter(tags=["Zones"])

@router.get("/zones")
async def get_zones():
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT id, name FROM zones ORDER BY id ASC")
            zones = cur.fetchall()
            print(f"DEBUG zones.py: Retrieved {len(zones)} zones")

        zones_list = list(zones)
        print(f"DEBUG zones.py: Returning zones: {zones_list}")
        return zones_list

    except Exception as e:
        print("Error fetching zones:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch zones")
