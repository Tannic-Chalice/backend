from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from typing import Optional
import os
import jwt
import boto3
from datetime import datetime

from app.database import get_db
# Ensure you import JWT_SECRET from your config to verify the signature
from app.config import JWT_SECRET 

router = APIRouter(tags=["Grievances"])

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

# Placeholder for Admin Actor ID (matches your Next.js admin.ts logic)
ADMIN_ID = 1 


# -------------------------------------------------------------------
# AUTHENTICATION HELPER (Restored & Fixed)
# -------------------------------------------------------------------
def decode_bwg_from_request(request: Request) -> str:
    """
    Extracts the token from Authorization Header or Cookie,
    verifies the JWT, and returns the User ID (bwg_id).
    """
    token = None
    
    # 1. Check Authorization Header (Priority for Capacitor/Mobile)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        val = auth_header.split(" ")[1]
        # Safety check for "undefined" string often sent by JS clients on error
        if val and val != "undefined" and val != "null":
            token = val

    # 2. Fallback to Cookie (For Web / Next.js Proxy)
    if not token:
        token = request.cookies.get("sessionToken-bwg")

    # 3. Validation: Check if token exists
    if not token:
        # Log for debugging (optional)
        # print(f"DEBUG: Grievances - No token found. Headers: {request.headers}")
        raise HTTPException(status_code=401, detail="Unauthorized - token missing")

    # 4. Validation: Verify JWT Signature
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Unauthorized - token expired")
    except jwt.InvalidTokenError as e:
        print(f"DEBUG: Grievances - Invalid Token: {token} | Error: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized - invalid token")

    # 5. Extract ID
    if not isinstance(decoded, dict) or "id" not in decoded:
        raise HTTPException(status_code=401, detail="Unauthorized - invalid payload")

    return str(decoded["id"])


async def upload_to_s3(file: UploadFile) -> str:
    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket missing")

    contents = await file.read()
    # Unique filename logic similar to your Next.js uuidv4 approach
    file_key = f"grievances/{datetime.utcnow().timestamp()}-{file.filename or 'attachment'}"
    
    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=file_key,
        Body=contents,
        ContentType=file.content_type or "application/octet-stream",
    )
    return f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_key}"


# -------------------------------------------------------------------
# 1) ADMIN: GET /grievances/admin 
# -------------------------------------------------------------------
@router.get("/admin")
def get_grievances_admin():
    # Matches admin.ts logic: Fetch all grievances with attachments
    query = """
        SELECT 
            g.id,
            g.ticket_display_id,
            g.title,
            g.description,
            g.category,
            g.status,
            g.incident_at,
            g.created_at,
            bwg.organization AS bwg_name,
            ga.file_url AS attachment_url
        FROM grievances g
        LEFT JOIN bwg bwg ON g.bwg_id = bwg.id
        LEFT JOIN grievance_attachments ga ON ga.grievance_id = g.id
        ORDER BY 
            CASE g.status
              WHEN 'Open' THEN 1
              WHEN 'In Progress' THEN 2
              WHEN 'Resolved' THEN 3
              WHEN 'Closed' THEN 4
            END,
            g.created_at DESC
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            grievances = [dict(zip(columns, row)) for row in rows]
        else:
            grievances = []

    return {"grievances": grievances}


@router.post("/admin")
async def update_grievance_admin(request: Request):
    # Matches admin.ts update logic
    body = await request.json()
    grievance_id = body.get("grievanceId")
    new_status = body.get("newStatus")
    admin_comment = body.get("adminComment") or ""

    if not grievance_id or not new_status:
        raise HTTPException(status_code=400, detail="Missing grievanceId or newStatus.")

    with get_db() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        try:
            # 1. Get old status
            cur.execute("SELECT status FROM grievances WHERE id = %s", (grievance_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Grievance not found.")
            old_status = row[0]

            # 2. Update status and timestamps
            update_query = """
                UPDATE grievances 
                SET 
                    status = %s::grievance_status,
                    resolved_at = CASE WHEN %s::grievance_status = 'Resolved' THEN NOW() ELSE resolved_at END,
                    closed_at = CASE WHEN %s::grievance_status = 'Closed' THEN NOW() ELSE closed_at END,
                    updated_at = NOW()
                WHERE id = %s
            """
            cur.execute(update_query, (new_status, new_status, new_status, grievance_id))

            # 3. Log action
            log_comment = f"Status changed to {new_status}. {admin_comment}".strip()
            cur.execute(
                """
                INSERT INTO grievance_logs (
                    grievance_id, actor_id, actor_type,
                    action, old_status, new_status, comment
                )
                VALUES (%s, %s, 'admin_user', 'Status Changed', %s, %s, %s)
                """,
                (grievance_id, ADMIN_ID, old_status, new_status, log_comment),
            )

            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Grievance updated successfully."}


# -------------------------------------------------------------------
# 2) CREATE: POST /grievances/create (Authenticated BWG)
# -------------------------------------------------------------------
@router.post("/create")
async def create_grievance(
    request: Request,
    category: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    incidentDate: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
):
    # 1. Authenticate & Get User ID
    user_id = decode_bwg_from_request(request)

    with get_db() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        try:
            # 2. Fetch User Location (Matches create.ts logic)
            cur.execute(
                """
                SELECT b.ward_name, b.zone_id, z.name AS zone_name
                FROM bwg b
                LEFT JOIN zones z ON b.zone_id = z.id
                WHERE b.id = %s
                """,
                (user_id,),
            )
            bwg_row = cur.fetchone()
            
            if not bwg_row:
                raise HTTPException(status_code=404, detail="BWG User details not found")

            ward_name, zone_id, zone_name = bwg_row

            # 3. Insert Grievance
            cur.execute(
                """
                INSERT INTO grievances (
                    bwg_id, title, description, category, incident_at,
                    ward_at_submission, zone_at_submission
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    user_id,
                    title,
                    description,
                    category,
                    incidentDate,
                    ward_name,
                    zone_name,
                ),
            )
            grievance_row = cur.fetchone()
            new_grievance_id = grievance_row[0]
            created_at = grievance_row[1]

            # 4. Generate & Update Ticket Display ID
            year = created_at.year if isinstance(created_at, datetime) else datetime.fromisoformat(str(created_at)).year
            ticket_display_id = f"BWG-{year}-{str(new_grievance_id).zfill(6)}"

            cur.execute(
                "UPDATE grievances SET ticket_display_id = %s WHERE id = %s",
                (ticket_display_id, new_grievance_id),
            )

            # 5. Handle Attachment
            file_url = None
            if attachment is not None:
                file_url = await upload_to_s3(attachment)
                cur.execute(
                    """
                    INSERT INTO grievance_attachments (
                        grievance_id, file_url, file_name, file_type
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        new_grievance_id,
                        file_url,
                        attachment.filename,
                        attachment.content_type,
                    ),
                )

            # 6. Log Creation
            cur.execute(
                """
                INSERT INTO grievance_logs (
                    grievance_id, actor_id, actor_type,
                    action, new_status, comment
                )
                VALUES (%s, %s, 'bwg_user', 'Ticket Created', 'Open', %s)
                """,
                (new_grievance_id, user_id, "Grievance submitted by user."),
            )

            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            print(f"Error creating grievance: {e}")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    return {
        "message": "Grievance created!",
        "grievance": {
            "id": new_grievance_id,
            "ticket_display_id": ticket_display_id,
            "title": title,
            "category": category,
            "status": "Open",
            "created_at": created_at,
        },
    }


# -------------------------------------------------------------------
# 3) LIST: GET /grievances/list (Authenticated BWG)
# -------------------------------------------------------------------
@router.get("/list")
def list_bwg_grievances(request: Request):
    # 1. Authenticate
    user_id = decode_bwg_from_request(request)

    # 2. Fetch User's Grievances (Matches list.ts)
    query = """
        SELECT
            id,
            ticket_display_id,
            title,
            category,
            status,
            created_at,
            ward_at_submission,
            zone_at_submission,
            supervisors_at_submission_id,
            vehicle_at_submission_id,
            driver_at_submission_id
        FROM grievances
        WHERE bwg_id = %s
        ORDER BY created_at DESC
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, (user_id,))
        rows = cur.fetchall()
        
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            grievances = [dict(zip(columns, row)) for row in rows]
        else:
            grievances = []

    return {"grievances": grievances}