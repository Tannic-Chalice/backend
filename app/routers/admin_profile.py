from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from app.database import get_db

router = APIRouter(prefix="/admin/profile", tags=["Admin Profile"])


# -----------------------
# Helper: Detect user type
# -----------------------
def detect_user_type(conn, user_id: str):
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM bwg WHERE id=%s LIMIT 1", (user_id,))
    if cur.fetchone():
        return "BWG"

    cur.execute("SELECT 1 FROM driver WHERE id=%s LIMIT 1", (user_id,))
    if cur.fetchone():
        return "Driver"

    if str(user_id).isdigit():
        cur.execute("SELECT 1 FROM supervisors WHERE id=%s LIMIT 1", (user_id,))
        if cur.fetchone():
            return "Supervisor"

    if str(user_id).isdigit():
        cur.execute("SELECT 1 FROM bswml_user WHERE bswml_id=%s LIMIT 1", (user_id,))
        if cur.fetchone():
            return "BSWML"

    return None


# -----------------------
# GET USER PROFILE
# -----------------------
@router.get("/{id}")
def get_profile(id: str, type: Optional[str] = Query(None)):
    with get_db() as conn:
        user_type = type or detect_user_type(conn, id)
        if not user_type:
            raise HTTPException(404, "User not found")

        cur = conn.cursor()

        if user_type == "BWG":
            query = """
                SELECT 
                    bwg.id, bwg.username, bwg.email, bwg.organization, bwg.phone,
                    bwg.person, bwg.location, bwg.address, bwg.generator_type, bwg.waste_types,
                    bwg.id_proof_url, bwg.org_photo_url, bwg.created_at, bwg.inspection_date, bwg.vendor,
                    bwg.remarks, bwg.consent, bwg.status, bwg.collection_time, bwg.segregation_methods,
                    bwg.daily_waste_kg, bwg.ward_id, bwg.ward_number, bwg.ward_name, bwg.zone,
                    bwg.zone_id, bwg.supervisor_id, bwg.price_per_kg, bwg.dry_waste_kg, bwg.wet_waste_kg,
                    'BWG' AS user_type
                FROM bwg
                WHERE bwg.id = %s
                LIMIT 1
            """
            cur.execute(query, (id,))

        elif user_type == "Driver":
            query = """
                SELECT 
                    id, username, gmail AS email, name AS full_name, phone_number AS phone,
                    license_number, ward_id, 'active' AS status, 'Driver' AS user_type
                FROM driver
                WHERE id=%s
                LIMIT 1
            """
            cur.execute(query, (id,))

        elif user_type == "Supervisor":
            query = """
                SELECT 
                    s.id, 
                    s.name AS username, 
                    s.gmail AS email, 
                    s.zone, 
                    s.ward_number, 
                    COALESCE(s.phone, '') AS phone, 
                    s.ward_name, 
                    s.driver_assigned, 
                    s.vehicle_assigned, 
                    s.created_at, 
                    s.updated_at,
                    z.id AS zone_id,  -- Fetched from the zones table
                    'active' AS status, 
                    'Supervisor' AS user_type
                FROM supervisors s
                LEFT JOIN zones z ON s.zone = z.name
                WHERE s.id = %s
                LIMIT 1
            """
            cur.execute(query, (id,))

        elif user_type == "BSWML":
            query = """
                SELECT 
                    bswml_id AS id, name, username, gmail AS email, phone,
                    govt_id, 'active' AS status, 'BSWML' AS user_type
                FROM bswml_user
                WHERE bswml_id=%s
                LIMIT 1
            """
            cur.execute(query, (id,))

        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "User not found")

        cols = [d[0] for d in cur.description]
        return {"user": dict(zip(cols, row))}

# -----------------------
# GET PICKUP ADDRESSES FOR BWG USER
# -----------------------
@router.get("/{id}/pickup-addresses")
def get_pickup_addresses(id: str, type: Optional[str] = Query(None)):
    with get_db() as conn:
        user_type = type or detect_user_type(conn, id)
        if not user_type:
            raise HTTPException(404, "User not found")

        if user_type != "BWG":
            return {"pickup_addresses": []}

        cur = conn.cursor()
        
        query = """
            SELECT DISTINCT ON (p.id)
                p.id, p.organization_name, p.contact_person, p.contact_number, 
                p.email, p.address, p.generator_type, p.waste_types, p.status, 
                p.created_at, p.location, p.inspection_date, p.avg_daily_qty, 
                p.existing_vendor, p.remarks, p.preferred_collection_time, 
                p.pincode, p.zone, p.ward, p.zone_id, p.price_per_kg,
                w.ward_number, w.ward_name,
                z.name AS zone_name
            FROM pickup_address p
            LEFT JOIN wards w ON p.ward::integer = w.ward_number
            LEFT JOIN zones z ON p.zone_id = z.id
            WHERE (p.bwg_id = %s OR p.id LIKE %s)
            ORDER BY p.id, p.created_at DESC
        """
        
        cur.execute(query, (id, f"{id}-P%"))
        rows = cur.fetchall()
        
        cols = [d[0] for d in cur.description]
        pickup_addresses = [dict(zip(cols, row)) for row in rows]
        
        return {"pickup_addresses": pickup_addresses}

# -----------------------
# UPDATE PICKUP ADDRESS FOR BWG
# -----------------------
@router.put("/{id}/pickup-addresses/{pickup_id}")
async def update_pickup_address(request: Request, id: str, pickup_id: str, type: Optional[str] = Query(None)):
    updates = await request.json()
    with get_db() as conn:
        user_type = type or detect_user_type(conn, id)
        if not user_type:
            raise HTTPException(404, "User not found")

        if user_type != "BWG":
            raise HTTPException(403, "Only BWG users can update pickup addresses")

        cur = conn.cursor()
        
        # Verify the pickup address belongs to this BWG user
        # Pickup IDs follow pattern: {BWGID}-P{N}, so verify the pickup_id starts with the user's ID
        if not str(pickup_id).startswith(f"{id}-P"):
            raise HTTPException(403, "Access denied - this pickup address does not belong to this user")

        # Verify the pickup address exists
        cur.execute("SELECT id FROM pickup_address WHERE id = %s", (pickup_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Pickup address not found")

        # Allowed fields for pickup address updates
        allowed = [
            "organization_name", "contact_person", "contact_number", "email", 
            "address", "generator_type", "waste_types", "location", "inspection_date",
            "avg_daily_qty", "existing_vendor", "remarks", "preferred_collection_time",
            "pincode", "status", "zone", "zone_id", "ward", "price_per_kg"
        ]

        # Filter updates to only allowed fields
        filtered_updates = {k: v for k, v in updates.items() if k in allowed}
        if not filtered_updates:
            raise HTTPException(400, "No valid fields to update")

        # Build update query
        fields = []
        values = []
        for field in allowed:
            if field in updates:
                fields.append(f"{field}=%s")
                values.append(updates[field])

        if not fields:
            raise HTTPException(400, "No valid fields to update")

        values.append(pickup_id)

        query = f"""
            UPDATE pickup_address
            SET {', '.join(fields)}
            WHERE id = %s
            RETURNING *;
        """

        try:
            cur.execute(query, tuple(values))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Pickup address not found")
            
            conn.commit()
            cols = [d[0] for d in cur.description]
            return {"pickup_address": dict(zip(cols, row)), "message": "Pickup address updated successfully"}
            
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Failed to update pickup address: {e}")
            raise HTTPException(500, f"Failed to update pickup address: {str(e)}")

# -----------------------
# UPDATE USER PROFILE
# -----------------------
@router.put("/{id}")
async def update_profile(request: Request, id: str, type: Optional[str] = Query(None)):
    updates = await request.json()
    with get_db() as conn:
        cur = conn.cursor()

        user_type = type or detect_user_type(conn, id)
        if not user_type:
            raise HTTPException(404, "User type not found")

        # Allowed fields by table
        if user_type == "BWG":
            table = "bwg"
            id_col = "id"
            allowed = [
                "username", "email", "organization", "phone", "person", "location",
                "address", "generator_type", "waste_types", "id_proof_url",
                "org_photo_url", "inspection_date", "ward_id", "ward_number", "ward_name", 
                "collection_time", "segregation_methods", "daily_waste_kg", "vendor", "remarks",
                "consent", "status", "price_per_kg", "zone", "zone_id", "supervisor_id"
            ]

        elif user_type == "Driver":
            table = "driver"
            id_col = "id"
            allowed = ["username", "gmail", "name", "phone_number", "license_number", "ward_id"]

            if "phone" in updates:
                updates["phone_number"] = updates.pop("phone")
            if "email" in updates:
                updates["gmail"] = updates.pop("email")

        elif user_type == "Supervisor":
            table = "supervisors"
            id_col = "id"
            allowed = ["name", "gmail", "zone", "ward_number", "ward_name", "phone",
                       "driver_assigned", "vehicle_assigned"]

            if "username" in updates:
                updates["name"] = updates.pop("username")
            if "email" in updates:
                updates["gmail"] = updates.pop("email")

        elif user_type == "BSWML":
            table = "bswml_user"
            id_col = "bswml_id"
            allowed = ["name", "username", "gmail", "phone", "govt_id"]

            if "email" in updates:
                updates["gmail"] = updates.pop("email")

        else:
            raise HTTPException(400, "Unknown user type")

        # Ensure type is provided and valid
        if not user_type:
            raise HTTPException(400, "User type is missing or invalid")

        # Enhanced error handling and logging
        if not updates:
            print("[ERROR] Empty or invalid JSON payload received.")
            raise HTTPException(400, "Payload is empty or invalid JSON")

        if not isinstance(updates, dict):
            print(f"[ERROR] Payload must be a JSON object. Received: {type(updates)}")
            raise HTTPException(400, "Payload must be a JSON object")

        print(f"[DEBUG] Validating fields for user type: {user_type}")
        invalid_fields = [field for field in updates if field not in allowed]
        if invalid_fields:
            print(f"[ERROR] Invalid fields detected: {invalid_fields}")
            raise HTTPException(400, f"Invalid fields in payload: {invalid_fields}")

        # Debug logs for Corporation and Supervisor updates
        if "zone" in updates:
            print(f"[DEBUG] Updating Corporation (zone): {updates['zone']}")
        if "supervisor_id" in updates:
            print(f"[DEBUG] Updating Supervisor ID: {updates['supervisor_id']}")

        # Validate allowed fields
        fields = []
        values = []

        for field in allowed:
            if field in updates:
                fields.append(f"{field}=%s")
                values.append(updates[field])

        if not fields:
            print("[ERROR] No valid fields to update in the payload.")
            raise HTTPException(400, "No valid fields to update")

        values.append(id)

        query = f"""
            UPDATE {table}
            SET {', '.join(fields)}
            WHERE {id_col}=%s
            RETURNING *;
        """

        print(f"[DEBUG] Update Profile Request: ID={id}, Type={type}, Payload={updates}")
        print(f"[DEBUG] Constructed SQL Query: {query}")
        print(f"[DEBUG] Values for SQL Query: {values}")

        cur.execute(query, tuple(values))
        row = cur.fetchone()

        if not row:
            raise HTTPException(404, "User not found")

        cols = [d[0] for d in cur.description]
        return {"user": dict(zip(cols, row)), "message": "User updated successfully"}

# -----------------------
# DELETE USER PROFILE
# -----------------------
@router.delete("/{id}")
def delete_user(id: str, type: Optional[str] = Query(None)):
    with get_db() as conn:
        user_type = type or detect_user_type(conn, id)
        if not user_type:
            raise HTTPException(404, "User not found")

        cur = conn.cursor()

        # Only allow deletion of BWG users
        if user_type != "BWG":
            raise HTTPException(403, f"Deletion not allowed for {user_type} users")

        # Delete the BWG user and related records
        try:
            # First, handle records that should be set to NULL instead of deleted
            # Set bwg_id to NULL in invoices
            cur.execute("DELETE FROM invoices WHERE bwg_id = %s", (id,))
            
            # Delete from tables that can be deleted
            # Delete grievances associated with this BWG user
            cur.execute("DELETE FROM grievances WHERE bwg_id = %s", (id,))
            
            # Delete billing contracts associated with this BWG user (if table exists)
            cur.execute("DELETE FROM billing_contracts WHERE bwg_id = %s", (id,))
            
            # Delete pickup addresses associated with this BWG user
            cur.execute("DELETE FROM pickup_address WHERE id LIKE %s", (f"{id}-P%",))
            
            # Delete pickups associated with this BWG user
            cur.execute("DELETE FROM pickups WHERE bwg_id = %s", (id,))
            
            # Finally, delete the BWG user
            cur.execute("DELETE FROM bwg WHERE id = %s RETURNING id", (id,))
            deleted_row = cur.fetchone()
            
            if not deleted_row:
                raise HTTPException(404, "BWG user not found")
            
            conn.commit()
            return {"message": "BWG user and all related records deleted successfully", "id": id}
            
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Failed to delete BWG user: {e}")
            raise HTTPException(500, f"Failed to delete user: {str(e)}")
