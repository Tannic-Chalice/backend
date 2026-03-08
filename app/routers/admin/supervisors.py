# app/routers/admin/supervisors.py

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from typing import Optional
from app.database import get_db
from psycopg2.extras import RealDictCursor
import jwt
import bcrypt
import os
from psycopg2.errors import UniqueViolation

router = APIRouter()

JWT_SECRET = os.getenv("JWT_SECRET", "")


def verify_admin_token(request: Request):
    # Try to get token from Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
    else:
        # Fall back to cookie
        token = request.cookies.get("sessionToken-admin")
    
    if not token:
        raise HTTPException(401, "Unauthorized: No token provided")
    
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {str(e)}")


@router.get("/supervisors")
def get_supervisors(request: Request, action: str = "list", auth=Depends(verify_admin_token)):
    if action == "list":
        try:
            with get_db() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    """
                    SELECT 
                        s.id, s.name, s.gmail, s.phone, s.zone, s.ward_number, s.ward_name,
                        s.driver_assigned, d.username AS driver_name,
                        s.vehicle_assigned, v.registration_number AS vehicle_registration,
                        s.created_at, s.updated_at
                    FROM supervisors s
                    LEFT JOIN driver d ON s.driver_assigned::text = d.id::text
                    LEFT JOIN vehicles v ON s.vehicle_assigned::text = v.vehicle_id::text
                    ORDER BY s.created_at DESC
                    """
                )
                supervisors = cur.fetchall()

            return {"supervisors": supervisors, "total": len(supervisors)}

        except Exception as e:
            print("Get supervisors error:", e)
            raise HTTPException(500, f"Internal Server Error: {str(e)}")
    
    elif action == "options":
        # ... (options logic stays exactly the same) ...
        try:
            with get_db() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("SELECT id AS driver_id, username AS driver_name FROM driver ORDER BY username")
                drivers = cur.fetchall()
                cur.execute("SELECT vehicle_id, registration_number FROM vehicles ORDER BY registration_number")
                vehicles = cur.fetchall()
                cur.execute("SELECT id AS zone_id, name AS zone_name FROM zones ORDER BY name")
                zones = cur.fetchall()
                cur.execute(
                    """
                    SELECT 
                        w.id AS ward_id, w.ward_number, w.ward_name, 
                        w.zone_id, z.name AS zone_name
                    FROM wards w
                    LEFT JOIN zones z ON w.zone_id = z.id
                    ORDER BY z.name, w.ward_number
                    """
                )
                wards = cur.fetchall()
            return {"drivers": drivers, "vehicles": vehicles, "zones": zones, "wards": wards}
        except Exception as e:
            raise HTTPException(500, f"Internal Server Error: {str(e)}")
    else:
        raise HTTPException(400, f"Invalid action: {action}")


@router.get("/supervisors/{id}")
def get_supervisor(id: str, request: Request, auth=Depends(verify_admin_token)):
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT 
                    s.id, s.name, s.gmail, s.phone, s.zone, s.ward_number, s.ward_name,
                    s.driver_assigned, d.username AS driver_name,
                    s.vehicle_assigned, v.registration_number AS vehicle_registration,
                    s.created_at, s.updated_at
                FROM supervisors s
                LEFT JOIN driver d ON s.driver_assigned::text = d.id::text
                LEFT JOIN vehicles v ON s.vehicle_assigned::text = v.vehicle_id::text
                WHERE s.id = %s
                """,
                (id,),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(404, "Supervisor not found")

        return {"supervisor": row}

    except Exception as e:
        print("Get supervisor error:", e)
        raise HTTPException(500, "Internal Server Error")

# ... (POST/create logic stays exactly the same) ...

@router.put("/supervisors")
async def update_supervisor(request: Request, auth=Depends(verify_admin_token)):
    data = await request.json()

    supervisor_id = data.get("id")
    name = data.get("name")
    # Capture phone and handle cases where it might be an empty string
    phone = data.get("phone")
    ward_id = data.get("ward_id")
    driver_assigned = data.get("driver_assigned")
    vehicle_assigned = data.get("vehicle_assigned")

    if not supervisor_id:
        raise HTTPException(400, "Supervisor ID is required")

    try:
        zone = ward_number = ward_name = None
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            if ward_id:
                cur.execute(
                    "SELECT w.ward_number, w.ward_name, z.name AS zone_name FROM wards w LEFT JOIN zones z ON w.zone_id = z.id WHERE w.id = %s",
                    (ward_id,),
                )
                ward_row = cur.fetchone()
                if not ward_row:
                    raise HTTPException(400, "Invalid ward selected")
                ward_number = ward_row['ward_number']
                ward_name = ward_row['ward_name']
                zone = ward_row['zone_name']

            driver_val = str(driver_assigned) if driver_assigned else None
            vehicle_val = str(vehicle_assigned) if vehicle_assigned else None
            
            ward_num_str = str(ward_number) if ward_number is not None else None
            ward_name_str = str(ward_name) if ward_name is not None else None
            zone_str = str(zone) if zone is not None else None
            cur.execute(
                """
                UPDATE supervisors
                SET name = COALESCE(%s, name),
                    phone = COALESCE(%s, phone),
                    zone = COALESCE(%s, zone),
                    ward_number = COALESCE(%s, ward_number),
                    ward_name = COALESCE(%s, ward_name),
                    driver_assigned = COALESCE(%s, driver_assigned),
                    vehicle_assigned = COALESCE(%s, vehicle_assigned),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, name, gmail, phone, zone, ward_number, ward_name, driver_assigned, vehicle_assigned
                """,
                (
                    name if name else None, 
                    phone if phone else None, 
                    zone_str, 
                    ward_num_str, 
                    ward_name_str, 
                    driver_val, 
                    vehicle_val, 
                    supervisor_id
                ),
            )
            updated = cur.fetchone()
            conn.commit()

        if not updated:
            raise HTTPException(404, "Supervisor not found")
        return {"message": "Supervisor updated successfully", "supervisor": updated}
    except Exception as e:
        print("Update supervisor error:", e)
        raise HTTPException(500, "Internal Server Error")


@router.delete("/supervisors/{id}")
def delete_supervisor(id: str, request: Request, auth=Depends(verify_admin_token)):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM supervisors WHERE id = %s RETURNING id", (id,))
            deleted = cur.fetchone()
            conn.commit()

        if not deleted:
            raise HTTPException(404, "Supervisor not found")

        return {"message": "Supervisor deleted successfully"}

    except Exception as e:
        print("Delete supervisor error:", e)
        raise HTTPException(500, "Internal Server Error")


@router.get("/supervisors/activity")
def get_activity(request: Request, supervisor_id: Optional[int] = None, auth=Depends(verify_admin_token)):
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            params = []
            where_clause = ""

            if supervisor_id:
                where_clause = "WHERE t.supervisor_id = %s"
                params.append(supervisor_id)

            cur.execute(
                f"""
                SELECT
                    t.trip_id,
                    t.status AS trip_status,
                    p.bwg_id,
                    b.organization,
                    b.daily_waste_kg,
                    p.updated_at AS pickup_date,
                    p.status AS pickup_status
                FROM trips t
                LEFT JOIN pickups p ON p.trip_id = t.trip_id
                LEFT JOIN bwg b ON p.bwg_id::text = b.id::text
                {where_clause}
                ORDER BY p.updated_at DESC NULLS LAST, t.trip_date DESC
                """,
                params,
            )

            rows = cur.fetchall()

        return {"activity": rows, "total": len(rows)}

    except Exception as e:
        print("Activity fetch error:", e)
        raise HTTPException(500, "Internal Server Error")
    
@router.post("/supervisors")
async def create_supervisor(
    request: Request,
    action: str = Query(None),
    auth=Depends(verify_admin_token)
):
    if action != "create":
        raise HTTPException(400, "Invalid action")

    data = await request.json()

    name = data.get("name")
    gmail = data.get("gmail")
    phone = data.get("phone")
    password = data.get("password")
    ward_id = data.get("ward_id")
    driver_assigned = data.get("driver_assigned")
    vehicle_assigned = data.get("vehicle_assigned")

    if not name or not gmail or not password or not ward_id:
        raise HTTPException(400, "Missing required fields")

    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute(
                """
                SELECT w.ward_number, w.ward_name, z.name AS zone_name
                FROM wards w
                LEFT JOIN zones z ON w.zone_id = z.id
                WHERE w.id = %s
                """,
                (ward_id,)
            )
            ward = cur.fetchone()

            if not ward:
                raise HTTPException(400, "Invalid ward selected")

            cur.execute(
                """
                INSERT INTO supervisors
                (
                    name, gmail, phone, password,
                    zone, ward_number, ward_name,
                    driver_assigned, vehicle_assigned,
                    created_at, updated_at
                )
                VALUES
                (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    NOW(), NOW()
                )
                RETURNING id, name, gmail, phone, zone,
                          ward_number, ward_name,
                          driver_assigned, vehicle_assigned,
                          created_at, updated_at
                """,
                (
                    name,
                    gmail,
                    phone,
                    hashed_password,
                    ward["zone_name"],
                    ward["ward_number"],
                    ward["ward_name"],
                    driver_assigned,
                    vehicle_assigned,
                ),
            )

            supervisor = cur.fetchone()

        return {
            "message": "Supervisor created successfully",
            "supervisor": supervisor
        }

    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Supervisor with this email already exists"
        )

    except HTTPException:
        raise

    except Exception as e:
        print("Create supervisor error:", e)
        raise HTTPException(500, "Internal Server Error")
