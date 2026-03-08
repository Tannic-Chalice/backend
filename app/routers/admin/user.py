# app/routers/admin/users.py

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from app.database import get_db

router = APIRouter()


@router.get("/users")
def get_all_users(search: Optional[str] = None):
    try:
        with get_db() as conn:
            cur = conn.cursor()

            # ---- Queries identical to your Next.js API ----
            bwg_query = """
                SELECT id, username, email, organization, phone, status, zone, created_at,
                       'BWG' AS user_type, 'bwg' AS auth_type
                FROM bwg
                ORDER BY created_at DESC
            """

            driver_query = """
                SELECT id, username, gmail AS email, name AS full_name,
                       phone_number AS phone, license_number, ward_id,
                       'active' AS status, 'Driver' AS user_type, 'driver' AS auth_type
                FROM driver
                ORDER BY id DESC
            """

            supervisor_query = """
                SELECT id, name AS username, gmail AS email, zone, ward_number, ward_name,
                       driver_assigned, vehicle_assigned, created_at, updated_at,
                       'active' AS status, 'Supervisor' AS user_type, 'supervisor' AS auth_type
                FROM supervisors
                ORDER BY created_at DESC
            """

            bswml_query = """
                SELECT bswml_id AS id, name, username, gmail AS email, phone, govt_id,
                       'active' AS status, 'BSWML' AS user_type, 'bswml' AS auth_type
                FROM bswml_user
                ORDER BY bswml_id DESC
            """

            # ---- Fetch all tables ----
            cur.execute(bwg_query)
            bwg_rows = cur.fetchall()

            cur.execute(driver_query)
            driver_rows = cur.fetchall()

            cur.execute(supervisor_query)
            supervisor_rows = cur.fetchall()

            cur.execute(bswml_query)
            bswml_rows = cur.fetchall()

        # ---- Convert rows into dictionaries ----
        users = []

        for row in bwg_rows:
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "organization": row[3],
                "phone": row[4],
                "status": row[5],
                "zone": row[6],
                "created_at": row[7],
                "user_type": row[8],
                "auth_type": row[9],
            })

        for row in driver_rows:
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "full_name": row[3],
                "phone": row[4],
                "status": row[7],
                "user_type": row[8],
                "auth_type": row[9],
            })

        for row in supervisor_rows:
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "zone": row[3],
                "ward_number": row[4],
                "ward_name": row[5],
                "driver_assigned": row[6],
                "vehicle_assigned": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "status": row[10],
                "user_type": row[11],
                "auth_type": row[12],
            })

        for row in bswml_rows:
            users.append({
                "id": row[0],
                "name": row[1],
                "username": row[2],
                "email": row[3],
                "phone": row[4],
                "status": row[6],
                "user_type": row[7],
                "auth_type": row[8],
            })

        # ---- Apply Search Filter ----
        if search:
            s = search.lower()

            def match(u):
                return (
                    s in str(u.get("id", "")).lower() or
                    s in str(u.get("username", "")).lower() or
                    s in str(u.get("email", "")).lower() or
                    s in str(u.get("organization", "")).lower() or
                    s in str(u.get("full_name", "")).lower()
                )

            users = list(filter(match, users))

        return users

    except Exception as e:
        print("Users fetch error:", e)
        raise HTTPException(500, "Internal Server Error")
