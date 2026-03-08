# app/routers/vehicles.py

from fastapi import APIRouter, HTTPException, Body, Query
from app.database import get_db

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


# -------------------------------------------------------------------------
# GET – List all vehicles
# -------------------------------------------------------------------------
@router.get("")
def list_vehicles():
    with get_db() as conn:
        cur = conn.cursor()
        query = """
            SELECT v.*, 
                   d.name AS driver_name, 
                   s.name AS supervisor_name, 
                   w.ward_name AS ward_name
            FROM vehicles v
            LEFT JOIN driver d ON v.driver_id = d.id
            LEFT JOIN supervisors s ON v.supervisor_id = s.id
            LEFT JOIN wards w ON v.ward_id = w.id
            ORDER BY v.created_at DESC
        """
        cur.execute(query)
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]


# -------------------------------------------------------------------------
# POST – Create vehicle
# -------------------------------------------------------------------------
@router.post("")
def create_vehicle(body: dict = Body(...)):
    registration_number = body.get("registration_number")
    vehicle_type = body.get("vehicle_type")
    driver_id = body.get("driver_id")
    supervisor_id = body.get("supervisor_id")
    ward_id = body.get("ward_id")
    corporation = body.get("corporation")

    if not registration_number:
        raise HTTPException(400, "registration_number required")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO vehicles 
            (registration_number, vehicle_type, driver_id, supervisor_id, ward_id, corporation)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                registration_number,
                vehicle_type,
                driver_id,
                supervisor_id,
                ward_id,
                corporation,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


# -------------------------------------------------------------------------
# PATCH – Update vehicle
# -------------------------------------------------------------------------
@router.patch("")
def update_vehicle(body: dict = Body(...)):
    vehicle_id = body.get("vehicle_id")
    if not vehicle_id:
        raise HTTPException(400, "vehicle_id required")

    allowed = {
        "registration_number",
        "vehicle_type",
        "driver_id",
        "supervisor_id",
        "ward_id",
        "corporation",
    }

    set_clauses = []
    values = []
    for key, value in body.items():
        if key == "vehicle_id":
            continue
        if key not in allowed:
            continue
        if isinstance(value, str) and value.strip() == "":
            value = None
        set_clauses.append(f"{key} = %s")
        values.append(value)

    if not set_clauses:
        raise HTTPException(400, "no valid fields to update")

    values.append(vehicle_id)

    with get_db() as conn:
        cur = conn.cursor()
        query = f"""
            UPDATE vehicles 
            SET {', '.join(set_clauses)}
            WHERE vehicle_id = %s
            RETURNING *
        """
        cur.execute(query, values)
        row = cur.fetchone()
        conn.commit()

        if not row:
            raise HTTPException(404, "Vehicle not found")

        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))


# -------------------------------------------------------------------------
# DELETE – Remove vehicle
# -------------------------------------------------------------------------
@router.delete("")
def delete_vehicle(id: str = Query(...)):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM vehicles WHERE vehicle_id = %s", (id,))
        conn.commit()
    return {"message": f"Vehicle {id} deleted"}
