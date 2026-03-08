from fastapi import APIRouter, HTTPException
from app.database import get_db

router = APIRouter()


@router.get("/assignment-data")
def admin_assignment_data():
    try:
        with get_db() as conn:
            cur = conn.cursor()

            # 1. Fetch Main BWGs
            cur.execute("""
                SELECT id AS id, organization AS name, location, 'MAIN_BWG' AS source_type
                FROM bwg
                WHERE status = 'approved'
                ORDER BY organization
            """)
            bwgs = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
            
            # 2. Fetch Additional Pickup Addresses
            cur.execute("""
                SELECT id AS id, organization_name AS name, location, 'ADDITIONAL_PICKUP' AS source_type
                FROM pickup_address
                WHERE status = 'approved'
            """)
            pickup_users = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]

            # 3. FIXED: Fetch Pickups (Handling both tables)
            # We use LEFT JOIN so rows aren't dropped if they don't exist in the bwg table
            # assignment_data.py

            cur.execute("""
                SELECT 
                    p.pickup_id,
                    p.scheduled_date,
                    p.scheduled_time_slot,
                    p.location,
                    p.status,
                    p.created_at,
                    p.updated_at,
                    -- LOGIC: Use source_type column to decide where to get the name
                    CASE 
                        WHEN p.source_type = 'ADDITIONAL_PICKUP' THEN (
                            SELECT pa.organization_name 
                            FROM pickup_address pa 
                            WHERE pa.id = p.bwg_id
                        )
                        ELSE (
                            SELECT b.organization 
                            FROM bwg b 
                            WHERE b.id = p.bwg_id
                        )
                    END AS bwg_id,
                    d.name AS driver_name,
                    v.registration_number AS vehicle_registration,
                    s.name AS supervisor_name
                FROM pickups p
                -- We use LEFT JOIN for trips/drivers so unassigned tasks still show up
                LEFT JOIN trips t ON p.trip_id = t.trip_id
                LEFT JOIN driver d ON t.driver_id = d.id
                LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                -- Use the supervisor from the trip, or fallback to p.supervisor_id if trip is null
                LEFT JOIN supervisors s ON COALESCE(t.supervisor_id, p.supervisor_id) = s.id
                WHERE p.status = 'PENDING'
                ORDER BY p.scheduled_date ASC, p.scheduled_time_slot ASC
            """)
            pickup_rows = cur.fetchall()
            pickup_cols = [d[0] for d in cur.description]
            pickups = [dict(zip(pickup_cols, r)) for r in pickup_rows]
            # 4. Drivers
            cur.execute("SELECT id AS driver_id, name AS full_name FROM driver ORDER BY name")
            drivers = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]

            # 5. Vehicles
            cur.execute("SELECT vehicle_id, registration_number FROM vehicles ORDER BY registration_number")
            vehicles = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]

        return {
            "pickups": pickups,
            "drivers": drivers,
            "vehicles": vehicles,
            "bwgs": bwgs + pickup_users
        }

    except Exception as e:
        print(f"Error fetching assignment data: {e}")
        raise HTTPException(status_code=500, detail=str(e))