from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor
from database import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/corporations")
def get_corporations():
    """
    Fetch all unique corporations (zones) for dropdown options.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT id, name
                FROM zones
                ORDER BY id
            """)

            zones = [{"id": row["id"], "name": row["name"]} for row in cur.fetchall()]
            cur.close()
            return {"corporations": zones}

    except Exception as e:
        logger.error(f"Error fetching corporations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/wards")
def get_wards():
    """
    Fetch all wards with combined ward number and name for dropdown options.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT id, CONCAT(ward_number, ' - ', ward_name) AS ward_info, zone_id, zone_name
                FROM wards
                ORDER BY ward_number
            """)

            wards = [{"id": row["id"], "ward_info": row["ward_info"], "zone_id": row["zone_id"], "zone_name": row["zone_name"]} for row in cur.fetchall()]
            cur.close()
            return {"wards": wards}

    except Exception as e:
        logger.error(f"Error fetching wards: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")