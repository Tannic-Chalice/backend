from fastapi import APIRouter, Request, HTTPException
from psycopg2 import connect
from psycopg2.extras import RealDictCursor
from typing import Dict, Any
import os

router = APIRouter(prefix="/api/user", tags=["User"])

def get_db():
    return connect(
        dsn=os.getenv("DATABASE_URL"),
        sslmode="require"
    )


@router.get("/{id}")
def get_user(id: str, request: Request):
    user_type = request.query_params.get("type")

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if not user_type:
            cur.execute("SELECT 1 FROM bwg WHERE id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "BWG"

        if not user_type:
            cur.execute("SELECT 1 FROM driver WHERE id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "Driver"

        if not user_type and id.isdigit():
            cur.execute("SELECT 1 FROM supervisors WHERE id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "Supervisor"

        if not user_type and id.isdigit():
            cur.execute("SELECT 1 FROM bswml_user WHERE bswml_id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "BSWML"

        if user_type == "BWG":
            query = """
                SELECT id, username, email, organization, phone, person, location, address,
                       generator_type, waste_types, id_proof_url, org_photo_url, created_at,
                       inspection_date, ward_number, ward_name, zone, supervisor_id, ward_id,
                       collection_time, segregation_methods, daily_waste_kg, vendor, remarks,
                       consent, status, 'BWG' as user_type
                FROM bwg WHERE id = %s LIMIT 1
            """
        elif user_type == "Driver":
            query = """
                SELECT id, username, gmail as email, name as full_name,
                    phone_number, phone_number AS phone,
                    license_number, ward_id, 'active' as status, 'Driver' as user_type
                FROM driver WHERE id = %s
            """
        elif user_type == "Supervisor":
            query = """
                SELECT id, name as username, gmail as email, zone, ward_number, ward_name, 
                COALESCE(phone, '') as phone,
                       driver_assigned, vehicle_assigned, created_at, updated_at, 
                       'active' as status, 'Supervisor' as user_type
                FROM supervisors WHERE id = %s 
            """
        elif user_type == "BSWML":
            query = """
                SELECT bswml_id as id, name, username, gmail as email, phone, govt_id,
                       'active' as status, 'BSWML' as user_type
                FROM bswml_user WHERE bswml_id = %s LIMIT 1
            """
        else:
            raise HTTPException(status_code=404, detail="User not found")

        cur.execute(query, (id,))
        user = cur.fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {"user": user}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        cur.close()
        conn.close()


@router.put("/{id}")
def update_user(id: str, updates: Dict[str, Any], request: Request):
    user_type = request.query_params.get("type")

    try:
        print(f"[DEBUG] Incoming updates for user {id}: {updates}")
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if not user_type:
            cur.execute("SELECT 1 FROM bwg WHERE id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "BWG"

        if not user_type:
            cur.execute("SELECT 1 FROM driver WHERE id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "Driver"

        if not user_type and id.isdigit():
            cur.execute("SELECT 1 FROM supervisors WHERE id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "Supervisor"

        if not user_type and id.isdigit():
            cur.execute("SELECT 1 FROM bswml_user WHERE bswml_id = %s LIMIT 1", (id,))
            if cur.fetchone():
                user_type = "BSWML"

        if user_type == "BWG":
            table = "bwg"
            allowed = [
                "username", "email", "organization", "phone", "person", "location", "address",
                "generator_type", "waste_types", "id_proof_url", "org_photo_url",
                "inspection_date", "ward_number", "ward_name", "zone", "supervisor_id",
                "ward_id", "collection_time", "segregation_methods", "daily_waste_kg",
                "vendor", "remarks", "consent", "status"
            ]
            id_col = "id"

        elif user_type == "Driver":
            table = "driver"
            allowed = ["username", "gmail", "name", "phone_number", "license_number", "ward_id"]
            id_col = "id"

            if "phone" in updates:
                updates["phone_number"] = updates.pop("phone")
            if "email" in updates:
                updates["gmail"] = updates.pop("email")

        elif user_type == "Supervisor":
            table = "supervisors"
            allowed = ["name", "gmail", "zone", "ward_number", "ward_name", "phone", "driver_assigned", "vehicle_assigned"]
            id_col = "id"

            if "username" in updates:
                updates["name"] = updates.pop("username")
            if "email" in updates:
                updates["gmail"] = updates.pop("email")

        elif user_type == "BSWML":
            table = "bswml_user"
            allowed = ["name", "username", "gmail", "phone", "govt_id"]
            id_col = "bswml_id"

            if "email" in updates:
                updates["gmail"] = updates.pop("email")

        else:
            raise HTTPException(status_code=404, detail="User type not found")

        fields = []
        values = []
        idx = 1

        for key in allowed:
            if key in updates:
                fields.append(f"{key} = %s")
                values.append(updates[key])
                idx += 1

        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        values.append(id)

        query = f"""
            UPDATE {table}
            SET {', '.join(fields)}
            WHERE {id_col} = %s
            RETURNING *
        """
        print(f"[DEBUG] SQL Query: {query}")
        print(f"[DEBUG] SQL Values: {values}")

        try:
            cur.execute(query, values)
            updated = cur.fetchone()
            conn.commit()
        except Exception as sql_e:
            print(f"[DEBUG] SQL Error: {sql_e}")
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"SQL Error: {sql_e}")

        if not updated:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user": updated,
            "message": "User updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        print(f"[DEBUG] General Error: {e}")
        raise HTTPException(status_code=500, detail=f"General Error: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
