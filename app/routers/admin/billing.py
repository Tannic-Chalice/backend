from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import jwt
from decimal import Decimal
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from calendar import monthrange
import uuid
from psycopg2.extras import RealDictCursor
from app.database import get_db
from app.config import JWT_SECRET
from app.services.auto_billing_service import run_auto_billing
router = APIRouter()

# =========================
# AUTH
# =========================
def decode_admin_user(request: Request):
    token = None

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        token = request.cookies.get("sessionToken-admin")

    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return decoded

def format_row(row):
    """Converts Decimal, UUID, and Date objects into JSON-safe formats."""
    if not row:
        return row
    new_row = dict(row)
    for key, value in new_row.items():
        if isinstance(value, Decimal):
            new_row[key] = float(value)
        elif isinstance(value, (uuid.UUID, date, datetime)):
            new_row[key] = str(value)
    return new_row

# =========================
# RESPONSE MODELS
# =========================
class BwgContractInfo(BaseModel):
    id: str
    contract_id: Optional[str]
    username: str
    organization: str
    default_amount: Optional[float]
    status: Optional[str]
    input_amount: Optional[str] = None


class BwgListResponse(BaseModel):
    bwgList: List[BwgContractInfo]


class SaveContractRequest(BaseModel):
    bwg_id: str
    default_amount: float


class ContractResponse(BaseModel):
    contract_id: str
    default_amount: float
    status: str
    next_invoice_date: Optional[date]


class SaveContractResponse(BaseModel):
    message: str
    contract: ContractResponse


class GenerateInvoiceRequest(BaseModel):
    bwg_id: str


# =========================
# GET BILLING LIST
# =========================
@router.get("/billing", response_model=BwgListResponse)
async def get_billing_list(request: Request):
    decode_admin_user(request)

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    b.id,
                    b.username,
                    b.organization,
                    bc.contract_id,
                    bc.default_amount,
                    bc.status
                FROM bwg b
                LEFT JOIN billing_contracts bc ON b.id = bc.bwg_id
                WHERE b.status = 'approved'
                ORDER BY b.organization, b.username
            """)
            rows = cur.fetchall()

        bwg_list = []
        for r in rows:
            amount = float(r[4]) if isinstance(r[4], Decimal) else r[4]
            bwg_list.append(BwgContractInfo(
                id=r[0],
                contract_id=str(r[3]) if r[3] else None,
                username=r[1],
                organization=r[2],
                default_amount=amount,
                status=r[5],
                input_amount=str(amount) if amount else ""
            ))

        return BwgListResponse(bwgList=bwg_list)

    except Exception as e:
        print("Billing list error:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch billing data")


# =========================
# SAVE / UPDATE CONTRACT
# =========================
@router.post("/billing", response_model=SaveContractResponse)
async def save_billing_contract(request: Request, body: SaveContractRequest):
    decode_admin_user(request)

    if body.default_amount < 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    IST = ZoneInfo("Asia/Kolkata")
    today = datetime.now(IST).date()

    if today.month == 12:
        next_invoice_date = date(today.year + 1, 1, 1)
    else:
        next_invoice_date = date(today.year, today.month + 1, 1)

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO billing_contracts
                (bwg_id, default_amount, next_invoice_date, status)
                VALUES (%s, %s, %s, 'ACTIVE')
                ON CONFLICT (bwg_id) DO UPDATE SET
                    default_amount = EXCLUDED.default_amount,
                    status = 'ACTIVE',
                    updated_at = NOW()
                RETURNING contract_id, default_amount, status, next_invoice_date
            """, (body.bwg_id, body.default_amount, next_invoice_date))

            row = cur.fetchone()
            conn.commit()

        return SaveContractResponse(
            message="Billing contract saved",
            contract=ContractResponse(
                contract_id=str(row[0]),
                default_amount=float(row[1]),
                status=row[2],
                next_invoice_date=row[3]
            )
        )

    except Exception as e:
        print("Save contract error:", e)
        raise HTTPException(status_code=500, detail="Failed to save contract")


# =========================
# MANUAL INVOICE (OPTIONAL)
# =========================
@router.put("/billing")
async def generate_invoice(request: Request, body: GenerateInvoiceRequest):
    decode_admin_user(request)

    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT contract_id, default_amount, invoice_counter
                FROM billing_contracts
                WHERE bwg_id = %s AND status = 'ACTIVE'
            """, (body.bwg_id,))

            contract = cur.fetchone()
            if not contract:
                raise HTTPException(status_code=404, detail="No active contract")

            contract_id, amount, counter = contract
            counter = counter or 1000
            new_counter = counter + 1

            invoice_number = f"INV-{body.bwg_id}-{new_counter}"
            issue_date = datetime.now().date()
            due_date = issue_date + timedelta(days=15)

            cur.execute("""
                INSERT INTO invoices
                (invoice_id, bwg_id, contract_id, invoice_number,
                 description, amount_due, issue_date, due_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()), body.bwg_id, contract_id,
                invoice_number, "Manual Invoice",
                amount, issue_date, due_date
            ))

            cur.execute("""
                UPDATE billing_contracts
                SET invoice_counter = %s
                WHERE contract_id = %s
            """, (new_counter, contract_id))

            conn.commit()

        return {"message": f"Invoice {invoice_number} created"}

    except Exception as e:
        print("Manual invoice error:", e)
        raise HTTPException(status_code=500, detail="Failed to generate invoice")


# =========================
# AUTO BILLING (CRON)
# =========================
@router.post("/billing/auto-generate")
async def auto_generate_billing():
    count = run_auto_billing()
    return {
        "message": "Auto billing completed",
        "generated_invoices": count
    }

@router.get("/invoices/{invoice_id}/transactions")
async def get_invoice_transactions(invoice_id: str, request: Request):
    # 1. Verify Admin Auth (using the same pattern as your other routes)
    decode_admin_user(request)

    try:
        with get_db() as conn:
            # Using RealDictCursor for cleaner object handling
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                
                # 2. Fetch Invoice Details with Organization Name
                cur.execute("""
                    SELECT i.*, b.organization as bwg_name 
                    FROM invoices i
                    JOIN bwg b ON i.bwg_id = b.id
                    WHERE i.invoice_id = %s
                """, (invoice_id,))
                invoice = cur.fetchone()
                
                if not invoice:
                    raise HTTPException(status_code=404, detail="Invoice not found")

                # 3. Fetch all related transactions (Success, Pending, or Failed)
                cur.execute("""
                    SELECT * FROM transactions 
                    WHERE invoice_id = %s 
                    ORDER BY paid_at DESC
                """, (invoice_id,))
                transactions = cur.fetchall()

                # 4. Return serialized data
                return {
                    "invoice": format_row(invoice),
                    "transactions": [format_row(tx) for tx in transactions]
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Admin Transaction Fetch Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/invoices/all")
async def get_all_invoices_admin(request: Request):
    """
    Fetches every invoice in the system so the Admin 
    can see the full billing history.
    """
    decode_admin_user(request) # Security check
    
    try:
        with get_db() as conn:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # We JOIN with bwg to get the organization name for the table
                cur.execute("""
                    SELECT i.*, b.organization as bwg_name 
                    FROM invoices i
                    JOIN bwg b ON i.bwg_id = b.id
                    ORDER BY i.created_at DESC
                """)
                rows = cur.fetchall()
                
                # Use the format_row helper we created earlier to handle Decimals/Dates
                return [format_row(r) for r in rows]
    except Exception as e:
        print(f"Error fetching all invoices: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")