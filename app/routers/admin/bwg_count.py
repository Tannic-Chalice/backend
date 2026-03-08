# app/routers/admin/bwg_count.py

from fastapi import APIRouter, HTTPException
from app.database import get_db

router = APIRouter()


@router.get("/bwgCount")
def admin_bwg_count():
    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM bwg")
            bwg_count = cur.fetchone()[0]

        return {
            "totalBWGs": bwg_count,
            "message": "BWG count fetched successfully"
        }

    except Exception as e:
        print("Error fetching BWG count:", e)
        raise HTTPException(500, "Internal Server Error")
