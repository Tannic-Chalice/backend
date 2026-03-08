from fastapi import APIRouter, HTTPException
from app.database import get_db

router = APIRouter()

@router.get("/overview")
def admin_overview():
    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM registrations")
            bwg_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM registrations WHERE status = 'pending'")
            pending_count = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM pickups 
                WHERE DATE(scheduled_date) = CURRENT_DATE 
                AND status = 'DONE'
            """)
            collections_today = cur.fetchone()[0]

        return {
            "totalBWGs": bwg_count,
            "pendingApprovals": pending_count,
            "collectionsToday": collections_today,
            "paymentsReceived": 0
        }

    except:
        raise HTTPException(500, "Internal Server Error")
