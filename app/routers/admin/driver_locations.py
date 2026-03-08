from fastapi import APIRouter, HTTPException, Request

from app.database import get_db
from app.config import JWT_SECRET
from app.routers.auth import get_token
import jwt


router = APIRouter()


def _require_admin(request: Request) -> None:
    """
    Minimal admin and bswml auth:
    - Reads the same JWT your /auth/login?action=admin or login?action=bswml endpoints issue.
    - Accepts token via Authorization: Bearer or sessionToken-admin/sessionToken-bswml cookie.
    - Verifies payload has role='admin' or role='bswml'.
    """
    token = get_token(request, "sessionToken-admin") or get_token(request, "sessionToken-bswml")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized - Token missing")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid token")

    if payload.get("role") not in ["admin", "bswml"]:
        raise HTTPException(status_code=403, detail="Forbidden - Insufficient role")



@router.get("/driver-locations")
def get_active_driver_locations(request: Request):
    _require_admin(request)

    # 1. Fixed "SSELECT" typo
    # 2. Optimized JOIN logic
    query = """
        SELECT DISTINCT ON (dll.driver_id)
            dll.driver_id,
            COALESCE(d.name, d.username) AS driver_name,
            dll.latitude AS lat,
            dll.longitude AS lng,
            dll.speed,
            dll.heading,
            dll.updated_at,
            t.status AS trip_status
        FROM driver_live_location AS dll
        JOIN driver AS d ON dll.driver_id = d.id
        LEFT JOIN trips AS t 
          ON t.driver_id = dll.driver_id
          AND t.trip_date = CURRENT_DATE
          AND t.status IN ('SCHEDULED', 'PENDING')
        ORDER BY dll.driver_id, dll.updated_at DESC, t.trip_id DESC;
    """

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description]

        result = []
        for r in rows:
            row_dict = dict(zip(cols, r))
            # Ensure trip_status is null if not present
            if row_dict.get('trip_status') is None:
                row_dict['trip_status'] = None
            result.append(row_dict)

        return result
    except Exception as e:
        import traceback
        print(f"Error fetching driver locations: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")