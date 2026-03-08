from fastapi import APIRouter, HTTPException
from app.database import get_db
from psycopg2.extras import RealDictCursor

router = APIRouter(tags=["lookups"])

# -------------------- GET VEHICLES --------------------
@router.get("/vehicles")
def get_vehicles():
    """Fetch all vehicles for dropdown"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT vehicle_id as id, registration_number as vehicle_number, vehicle_type
                FROM vehicles
                ORDER BY registration_number ASC
            """)
            vehicles = cur.fetchall()
            return [dict(v) for v in vehicles]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- GET DRIVERS --------------------
@router.get("/drivers")
def get_drivers():
    """Fetch all drivers for dropdown"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT id, name as full_name
                FROM driver
                ORDER BY name ASC
            """)
            drivers = cur.fetchall()
            return [dict(d) for d in drivers]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- GET SUPERVISORS --------------------
@router.get("/supervisor-list")
def get_supervisors():
    """Fetch all supervisors for dropdown"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT id, name as full_name
                FROM supervisors
                ORDER BY name ASC
            """)
            supervisors = cur.fetchall()
            return [dict(s) for s in supervisors]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- GET WARDS --------------------
@router.get("/wards")
def get_wards():
    """Fetch all wards for dropdown with ward number and zone info"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT id, ward_number, ward_name, zone_id, zone_name
                FROM wards
                ORDER BY ward_number ASC
            """)
            wards = cur.fetchall()
            return [dict(w) for w in wards]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- GET WEIGH BRIDGES --------------------
@router.get("/weigh-bridges")
def get_weigh_bridges():
    """Fetch all weigh bridges for dropdown"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Return vehicle_numbers from weigh_bridge_data as weigh bridge identifiers
            cur.execute("""
                SELECT DISTINCT 
                    row_number() OVER (ORDER BY vehicle_number) as id, 
                    vehicle_number as name
                FROM weigh_bridge_data
                ORDER BY vehicle_number ASC
            """)
            weigh_bridges = cur.fetchall()
            return [dict(wb) for wb in weigh_bridges] if weigh_bridges else []
    except Exception as e:
        # If error, return empty list gracefully
        return []
