# app/routers/drivers.py

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from app.database import get_db
import bcrypt
import secrets
from datetime import datetime, timedelta

router = APIRouter(prefix="/driver", tags=["Driver"])


def sanitize_username(val: str) -> str:
    return "".join(ch for ch in val.lower() if ch.isalnum())[:32]


# -----------------------------------------------------------------------------
# GET – List drivers
# -----------------------------------------------------------------------------
@router.get("")
def list_drivers():
    with get_db() as conn:
        cur = conn.cursor()
        query = """
            SELECT d.*, w.ward_name
            FROM driver d
            LEFT JOIN wards w ON d.ward_id = w.id
            ORDER BY d.name
        """
        cur.execute(query)
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]


# -----------------------------------------------------------------------------
# POST – Create driver
# -----------------------------------------------------------------------------
@router.post("")
def create_driver(body: dict = Body(...)):
    name = body.get("name")
    phone_number = body.get("phone_number")
    license_number = body.get("license_number")
    gmail = body.get("gmail")
    ward_id = body.get("ward_id")

    if not gmail or not license_number:
        raise HTTPException(400, "gmail and license_number required")

    base = sanitize_username(gmail.split("@")[0])
    if not base:
        base = "driver"

    with get_db() as conn:
        cur = conn.cursor()

        # ensure unique username
        username = base
        counter = 0
        while True:
            cur.execute("SELECT 1 FROM driver WHERE username=%s", (username,))
            if cur.fetchone() is None:
                break
            counter += 1
            username = f"{base}{counter}"

        # generate temporary password
        temp_password = secrets.token_hex(6)
        hashed = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

        try:
            cur.execute(
                """
                INSERT INTO driver (username, name, phone_number, license_number, gmail, ward_id, password)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    username,
                    name,
                    phone_number,
                    license_number,
                    gmail,
                    ward_id,
                    hashed,
                ),
            )
            row = cur.fetchone()
            conn.commit()

            cols = [d[0] for d in cur.description]
            driver_data = dict(zip(cols, row))
            driver_data["tempPassword"] = temp_password

            return driver_data

        except Exception as e:
            if "duplicate key" in str(e):
                raise HTTPException(409, "Driver already exists")
            raise HTTPException(500, f"DB error: {str(e)}")


# -----------------------------------------------------------------------------
# PATCH – Update driver
# -----------------------------------------------------------------------------
@router.patch("")
def update_driver(body: dict = Body(...)):
    driver_id = body.get("id")
    if not driver_id:
        raise HTTPException(400, "id is required")

    allowed = {
        "username",
        "name",
        "phone_number",
        "license_number",
        "gmail",
        "ward_id",
        "password",
    }

    set_clause = []
    values = []
    for key, val in body.items():
        if key == "id":
            continue
        if key not in allowed:
            continue

        if isinstance(val, str) and val.strip() == "":
            val = None

        set_clause.append(f"{key} = %s")
        values.append(val)

    if not set_clause:
        raise HTTPException(400, "No valid fields to update")

    values.append(driver_id)

    with get_db() as conn:
        cur = conn.cursor()
        query = f"""
            UPDATE driver
            SET {', '.join(set_clause)}
            WHERE id = %s
            RETURNING *
        """
        cur.execute(query, values)
        row = cur.fetchone()
        conn.commit()

        if not row:
            raise HTTPException(404, "Driver not found")

        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))


# -----------------------------------------------------------------------------
# DELETE – Remove driver
# -----------------------------------------------------------------------------
@router.delete("")
def delete_driver(id: str = Query(...)):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM driver WHERE id=%s", (id,))
        conn.commit()
        return {"message": f"Driver {id} deleted"}


# -----------------------------------------------------------------------------
# PUT?action=generate_link – Generate Login Link
# -----------------------------------------------------------------------------
@router.put("")
def generate_link(action: str = Query(None), body: dict = Body(None)):
    if action != "generate_link":
        raise HTTPException(405, "Invalid action")

    driver_id = body.get("id")
    if not driver_id:
        raise HTTPException(400, "id is required")

    token = secrets.token_hex(48)
    expires_at = datetime.utcnow() + timedelta(hours=24)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO driver_tokens (driver_id, token, expires_at)
            VALUES (%s,%s,%s)
            """,
            (driver_id, token, expires_at),
        )
        conn.commit()

    base = ""  # you may load from env if needed
    link = f"{base}/driver/login?token={token}&id={driver_id}"

    return {"token": token, "url": link, "expiresAt": expires_at}
