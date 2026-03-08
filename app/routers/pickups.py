from fastapi import APIRouter, HTTPException, Request
from app.database import get_db
from app.config import JWT_SECRET
import jwt

router = APIRouter(tags=["Pickups"])


@router.get("/history")
async def get_bwg_pickup_history(request: Request):
    auth_header = request.headers.get("Authorization")
    token = None

    # 1. Check Header (Capacitor)
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    # 2. Check Cookie (Fallback)
    if not token:
        token = request.cookies.get("sessionToken-bwg")

    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized: No token provided")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Unauthorized: {str(e)}")

    if not isinstance(decoded, dict) or "id" not in decoded:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token payload")

    bwg_id = decoded["id"]

    query = """
        SELECT 
            p.pickup_id, 
            p.scheduled_date AS pickup_date,
            p.actual_pickup_timestamp, 
            p.status,
            v.registration_number AS vehicle_number,
            d.name AS driver_name,
            t.driver_id,
            t.status AS trip_status,
            b.id AS location_id,
            b.organization AS organization_name
        FROM pickups p  
        JOIN trips t ON p.trip_id = t.trip_id
        JOIN vehicles v ON t.vehicle_id = v.vehicle_id
        LEFT JOIN driver d ON t.driver_id = d.id
        JOIN bwg b ON p.bwg_id = b.id
        WHERE p.bwg_id = %s AND p.scheduled_date <= CURRENT_DATE
        
        UNION ALL
        
        SELECT 
            p.pickup_id, 
            p.scheduled_date AS pickup_date,
            p.actual_pickup_timestamp, 
            p.status,
            v.registration_number AS vehicle_number,
            d.name AS driver_name,
            t.driver_id,
            t.status AS trip_status,
            pa.id AS location_id,
            pa.organization_name AS organization_name
        FROM pickups p  
        JOIN trips t ON p.trip_id = t.trip_id
        JOIN vehicles v ON t.vehicle_id = v.vehicle_id
        LEFT JOIN driver d ON t.driver_id = d.id
        JOIN pickup_address pa ON p.bwg_id = SPLIT_PART(pa.id, '-', 1)
        WHERE p.bwg_id = %s AND p.scheduled_date <= CURRENT_DATE
        
        ORDER BY pickup_date DESC;
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, (bwg_id, bwg_id))
        rows = cur.fetchall()

    pickups = [
        {
            "pickup_id": row[0],
            "pickup_date": str(row[1]),
            "actual_pickup_timestamp": str(row[2]) if row[2] else None,
            "status": row[3],
            "vehicle_number": row[4],
            "driver_name": row[5],
            "driver_id": row[6],
            "trip_status": row[7],
            "location_id": row[8],
            "organization_name": row[9],
        }
        for row in rows
    ]

    return {"pickups": pickups}


@router.get("/live-driver-location")
async def get_bwg_live_driver_location(request: Request, driverId: int):
    """Get live location for a specific driver from driver_live_location table."""
    auth_header = request.headers.get("Authorization")
    token = None

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        token = request.cookies.get("sessionToken-bwg")

    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized: No token provided")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Unauthorized: {str(e)}")

    if not isinstance(decoded, dict) or "id" not in decoded:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token payload")

    bwg_id = decoded["id"]

    # Simple query to get latest driver location
    query = """
        SELECT
            dll.driver_id,
            COALESCE(d.name, d.username) AS driver_name,
            dll.latitude AS lat,
            dll.longitude AS lng,
            dll.updated_at
        FROM driver_live_location AS dll
        LEFT JOIN driver AS d ON dll.driver_id = CAST(d.id AS VARCHAR)
        WHERE dll.driver_id = %s
        ORDER BY dll.updated_at DESC
        LIMIT 1;
    """

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(query, (str(driverId),))
            row = cur.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Driver location not available"
            )

        return {
            "driver_id": row[0],
            "driver_name": row[1],
            "lat": float(row[2]),
            "lng": float(row[3]),
            "updated_at": row[4],
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in live-driver-location: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )