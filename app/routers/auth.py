from fastapi import APIRouter, HTTPException, Request, Response, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional
import jwt
import httpx
import os
from app.database import get_db
from app.config import JWT_SECRET, _get_cookie_settings
from app.services.password_utils import verify_password, hash_password
from app.services.jwt_utils import create_token
from app.services.google_oauth import verify_google_token


router = APIRouter(tags=["Auth"])

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def get_token(request: Request, cookie_name: str) -> str:
    """Helper to get token from Header OR Cookie"""
    
    # 1. Check Authorization Header (Prioritize this for Capacitor/Mobile)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        val = auth_header.split(" ")[1]
        # Avoid "undefined" string if frontend bugs out
        if val and val != "undefined" and val != "null":
            return val
    
    # 2. Check Cookie (Fallback for Web)
    return request.cookies.get(cookie_name)


def decode_bwg_from_cookie(request: Request) -> str:
    token = get_token(request, "sessionToken-bwg")

    if not token:
        # Debugging
        # print(f"DEBUG: No token found. Headers: {request.headers}")
        raise HTTPException(status_code=401, detail="Unauthorized - Token missing")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception as e:
        print(f"DEBUG: Token decode failed: {e} | Token was: {token}")
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid token")

    if "id" not in decoded:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return str(decoded["id"])

def decode_supervisor_from_cookie(request: Request) -> str:
    token = get_token(request, "sessionToken-supervisor")

    if not token:
        # Debugging
        # print(f"DEBUG: No token found. Headers: {request.headers}")
        raise HTTPException(status_code=401, detail="Unauthorized - Token missing")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception as e:
        print(f"DEBUG: Token decode failed: {e} | Token was: {token}")
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid token")

    if "id" not in decoded:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return str(decoded["supervisor_id"])


def decode_driver_id_from_cookie(request: Request) -> int:
    token = get_token(request, "sessionToken-driver")
    
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized - Token missing")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if "driver_id" not in decoded:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return int(decoded["driver_id"])

# ------------------------------------------------------------------
# LOGIN FUNCTIONS (UPDATED TO RETURN TOKEN IN BODY)
# ------------------------------------------------------------------

def admin_login(body: dict, response: Response):
    username = body.get("username")
    password = body.get("password")

    if not username or not password:
        raise HTTPException(400, "Username and password are required")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM admins WHERE username=%s", (username,))
        row = cur.fetchone()

    if not row or not verify_password(password, row[0]):
        raise HTTPException(401, "Invalid credentials")

    token = create_token({"username": username, "role": "admin"}, hours=8)

    # We return the token explicitly for the frontend to save
    return {"message": "Login successful", "token": token}


def bwg_login(body: dict, response: Response):
    username = body.get("username")
    password = body.get("password")

    if not username or not password:
        return JSONResponse(status_code=400, content={"message": "Username / Email and password are required"})

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, password, status, email
            FROM bwg
            WHERE username=%s OR email=%s
            LIMIT 1
        """, (username, username))
        row = cur.fetchone()

    if not row:
        return JSONResponse(status_code=401, content={"message": "Invalid credentials"})

    uid, hashed, status, email = row

    if not verify_password(password, hashed):
        return JSONResponse(status_code=401, content={"message": "Invalid credentials"})

    token = create_token({"id": uid, "status": status, "email": email or username, "role": "BWG"})

    # FIXED: Return the token in the body!
    return {
        "message": "Login successful",
        "token": token, 
        "status": status
    }


def google_bwg_login(body: dict, response: Response):
    google_id_token = body.get("token")
    if not google_id_token:
        raise HTTPException(400, "Token is required")

    # 1. Verify Google Token
    google_user = verify_google_token(google_id_token)
    email = google_user.get("email")
    username = email.split("@")[0]

    with get_db() as conn:
        cur = conn.cursor()
        
        # 2. Check if user exists
        cur.execute("SELECT id, email, status FROM bwg WHERE email=%s LIMIT 1", (email,))
        existing = cur.fetchone()

        if existing:
            # User exists: Use existing DB data
            uid, email_db, status = existing
        else:
            # User does not exist: Create new account (Signup)
            cur.execute("SELECT nextval('bwg_custom_id_seq')")
            next_id = cur.fetchone()[0]
            custom_id = f"ORI{str(next_id).zfill(4)}"

            cur.execute("""
                INSERT INTO bwg (id, email, username, password, status)
                VALUES (%s, %s, %s, NULL, 'signup')
                RETURNING id, email, status
            """, (custom_id, email, username))

            row = cur.fetchone()
            conn.commit()
            uid, email_db, status = row

    # 3. Create Token (Matches bwg_login structure exactly)
    # Payload keys: id, status, email, role
    token = create_token({
        "id": uid, 
        "status": status, 
        "email": email_db, 
        "role": "BWG"
    })

    # 4. Return Response (Matches bwg_login structure)
    return {
        "message": "Login successful" if existing else "Signup successful",
        "token": token,
        "status": status
    }

DEMO_PHONE = "9999999999"
DEMO_OTP = "123456"

def driver_login(body: dict, response: Response):
    phone = body.get("phone")

    if not phone:
        raise HTTPException(400, "Phone number is required")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM driver WHERE phone_number=%s LIMIT 1",
            (phone,)
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(404, "Driver not registered")

    driver_id = row[0]

    token = create_token({
        "driver_id": driver_id,
        "phone": phone,
        "role": "driver"
    })

    # ✅ DEMO ACCOUNT BYPASS (Play Store)
    if phone == DEMO_PHONE:
        return {
            "message": "Demo login OTP accepted",
            "token": token,
            "otp": DEMO_OTP,          # optional: useful for frontend demo
            "is_demo": True
        }

    # 🔐 NORMAL OTP FLOW
    try:
        httpx.post(
            f"{os.getenv('BACKEND_URL')}/otp/send",
            json={"phone": phone},
            timeout=3  # fire-and-forget
        )
    except Exception as e:
        print("OTP SEND WARNING (ignored):", e)

    return {
        "message": "OTP sent successfully",
        "token": token
    }

def supervisor_login(body: dict, response: Response):
    phone = body.get("phone")

    if not phone:
        raise HTTPException(400, "Phone number is required")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM supervisors WHERE phone=%s LIMIT 1",
            (phone,)
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(404, "Driver not registered")
    supervisor_id = row[0]

    token = create_token({"supervisor_id": supervisor_id, "phone": phone, "role": "supervisor" })
    if phone == DEMO_PHONE:
        return {
            "message": "Demo login OTP accepted",
            "token": token,
            "otp": DEMO_OTP,          # optional: useful for frontend demo
            "is_demo": True
        }
    try:
        httpx.post(
            f"{os.getenv('BACKEND_URL')}/otp/send",
            json={"phone": phone},
            timeout=3  # short timeout, fire-and-forget
        )
        return {"message": "OTP sent successfully", "token": token }

    except Exception as e:
        print("OTP SEND WARNING (ignored):", e)
        # ❗ Do NOT fail here

    return {
        "message": "OTP sent successfully", "token": token
    }

# def google_driver_login(body: dict, response: Response):
#     token_value = body.get("token")
#     google_user = verify_google_token(token_value)
#     email = google_user.get("email")

#     with get_db() as conn:
#         cur = conn.cursor()
#         cur.execute("SELECT id FROM driver WHERE gmail=%s", (email,))
#         row = cur.fetchone()

#     if not row:
#         raise HTTPException(404, "Account does not exist")

#     driver_id = row[0]
#     token = create_token({"driver_id": driver_id, "email": email})

#     # FIXED: Return token in body
#     return {
#         "message": "Login successful",
#         "token": token
#     }


# def google_admin_login(body: dict, response: Response):
#     token_value = body.get("token")
#     google_user = verify_google_token(token_value)
#     email = google_user.get("email")

#     with get_db() as conn:
#         cur = conn.cursor()
#         cur.execute("SELECT id FROM admins WHERE gmail=%s", (email,))
#         row = cur.fetchone()

#     if not row:
#         raise HTTPException(404, "Account does not exist")

#     admin_id = row[0]
#     token = create_token({"admin_id": admin_id, "email": email})

#     # FIXED: Return token in body
#     return {
#         "message": "Login successful",
#         "token": token
#     }


def bswml_login(body: dict, response: Response):
    identifier = body.get("username")  # can be username or email
    password = body.get("password")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT bswml_id, password, name, gmail
            FROM bswml_user
            WHERE username = %s OR gmail = %s
            """,
            (identifier, identifier)
        )
        row = cur.fetchone()

    # Invalid credentials
    if not row or not verify_password(password, row[1]):
        raise HTTPException(401, "Invalid credentials")

    bswml_id, password, name, gmail = row

    token = create_token({
        "id": bswml_id,
        "email": gmail,
        "role": "admin"
    })

    return {
        "message": "Login successful",
        "token": token,
        "username": identifier,
        "name": name
    }


# def google_bswml_login(body: dict, response: Response):
#     token_value = body.get("token")
#     google_user = verify_google_token(token_value)
#     email = google_user.get("email")

#     with get_db() as conn:
#         cur = conn.cursor()
#         cur.execute("SELECT bswml_id FROM bswml_user WHERE gmail=%s", (email,))
#         row = cur.fetchone()

#     if not row:
#         raise HTTPException(404, "Account does not exist")

#     token = create_token({"id": row[0], "email": email})

#     # FIXED: Return token in body
#     return {
#         "message": "Login successful",
#         "token": token
#     }


@router.post("/login")
async def login(request: Request, response: Response, action: str = Query(...)):
    body = await request.json()

    if action == "admin":
        return admin_login(body, response)
    if action == "bwg":
        return bwg_login(body, response)
    if action == "driver":
        return driver_login(body, response)
    if action == "googleDriver":
        return google_driver_login(body, response)
    if action == "googleAdmin":
        return google_admin_login(body, response)
    if action == "googleBWG":
        return google_bwg_login(body, response)
    if action == "bswml":
        return bswml_login(body, response)
    if action == "googleBSWML":
        return google_bswml_login(body, response)
    if action == "supervisor":
        return supervisor_login(body, response)
    raise HTTPException(400, "Invalid action")


class OldPasswordChangeBody(BaseModel):
    oldPassword: str
    newPassword: str


class NewPasswordResetBody(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    newPassword: str


@router.post("/change-pwd")
async def change_password(request: Request, action: str = Query(...)):
    with get_db() as conn:
        cur = conn.cursor()

        if action == "old":
            body = await request.json()
            data = OldPasswordChangeBody(**body)
            user_id = decode_bwg_from_cookie(request)

            cur.execute("SELECT password FROM bwg WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row or not verify_password(data.oldPassword, row[0]):
                return JSONResponse(status_code=401, content={"message": "Old password incorrect"})
                
            hashed = hash_password(data.newPassword)
            cur.execute("UPDATE bwg SET password = %s WHERE id = %s", (hashed, user_id))
            conn.commit()

            return {"message": "Password changed successfully"}

        if action == "new":
            body = await request.json()
            data = NewPasswordResetBody(**body)

            if data.email:
                cur.execute("SELECT id FROM bwg WHERE email=%s", (data.email,))
            else:
                cur.execute("SELECT id FROM bwg WHERE phone=%s", (data.phone,))

            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Account not found")

            hashed = hash_password(data.newPassword)

            if data.email:
                cur.execute("UPDATE bwg SET password=%s WHERE email=%s", (hashed, data.email))
            else:
                cur.execute("UPDATE bwg SET password=%s WHERE phone=%s", (hashed, data.phone))

            conn.commit()
            return {"message": "Password reset successful"}

        raise HTTPException(400, "Invalid action")


@router.post("/logout")
async def logout(response: Response, action: str = Query(...)):
    # We can still clear server-side cookies just in case, but client-side token deletion is key
    if action == "admin":
        response.delete_cookie("admin_logged_in")
        response.delete_cookie("sessionToken-admin")
    elif action == "bwg":
        response.delete_cookie("bwg_logged_in")
        response.delete_cookie("sessionToken-bwg")
    elif action == "driver":
        response.delete_cookie("driver_logged_in")
        response.delete_cookie("sessionToken-driver")
    else:
        raise HTTPException(400, "Invalid action")

    return {"message": "Logout successful"}


class BwgSignupBody(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    googleToken: Optional[str] = None


@router.post("/signup")
async def bwg_signup(request: Request):
    body = await request.json()
    email = body.get("email")
    password = body.get("password")        # Optional
    google_token = body.get("googleToken") # Optional
    phone = body.get("phone")

    if not email and not google_token:
        raise HTTPException(400, "Email or Google token required")

    with get_db() as conn:
        cur = conn.cursor()

        # ---------------- Google signup ----------------
        if google_token:
            google_user = verify_google_token(google_token)
            email = google_user["email"]

        # ---------------- Optional password handling ----------------
        hashed_password = hash_password(password) if password else None

        username = email.split("@")[0]

        # Check if account already exists
        cur.execute(
            "SELECT id, status FROM bwg WHERE email=%s LIMIT 1",
            (email,)
        )
        existing = cur.fetchone()
        if existing:
            uid, status = existing
            token = create_token({
                "id": uid,
                "email": email,
                "status": status,
                "role": "BWG"
            })
            return {
                "message": "Account already exists",
                "status": "exists",
                "token": token
            }

        # Generate custom ID
        cur.execute("SELECT nextval('bwg_custom_id_seq')")
        next_id = cur.fetchone()[0]
        custom_id = f"ORI{str(next_id).zfill(4)}"

        # Insert into database
        cur.execute(
            """
            INSERT INTO bwg (id, email, password, status, username, phone)
            VALUES (%s, %s, %s, 'signup', %s, %s)
            """,
            (custom_id, email, hashed_password, username, phone)
        )

        conn.commit()

        # Create token after signup
        token = create_token({
            "id": custom_id,
            "email": email,
            "status": "signup",
            "role": "BWG"
        })

        return {
            "message": "Signup successful",
            "status": "created",
            "token": token
        }


@router.get("/profile")
async def profile(request: Request, action: str = Query(...)):
    with get_db() as conn:
        cur = conn.cursor()

        if action == "bwg":
            user_id = decode_bwg_from_cookie(request)
            
            cur.execute("""
                SELECT id, organization, person, phone, location, address, email,
                       waste_types, generator_type, id_proof_url, status,
                       org_photo_url, inspection_date
                FROM bwg WHERE id=%s
            """, (user_id,))
            
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "User profile not found")

            columns = [d[0] for d in cur.description]
            return dict(zip(columns, row))

        if action == "driver":
            driver_id = str(decode_driver_id_from_cookie(request))
            
            cur.execute("""
                SELECT id, name, gmail, license_number, phone_number
                FROM driver WHERE id=%s
            """, (driver_id,))
            
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "User profile not found")

            columns = [d[0] for d in cur.description]
            return dict(zip(columns, row))

        raise HTTPException(400, "Invalid action")