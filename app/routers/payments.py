from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Any
import razorpay
import hmac
import hashlib
import jwt
import json
from decimal import Decimal

from app.database import get_db
from app.config import JWT_SECRET, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET

router = APIRouter()

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# Helper function to decode BWG user from JWT
def decode_bwg_user(request: Request):
    """
    Extract and decode the JWT token from Authorization header or cookie.
    Returns the decoded user data.
    """
    token = None
    
    # Check Authorization Header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # Fallback to Cookie
    if not token:
        token = request.cookies.get("sessionToken-bwg")
    
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized - No valid token found")
    
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Unauthorized - Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid token")
    
    if not isinstance(decoded, dict) or "id" not in decoded:
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid token payload")
    
    return decoded


# Request/Response Models
class CreateOrderRequest(BaseModel):
    invoice_id: str


class CreateOrderResponse(BaseModel):
    order_id: str
    key: str
    amount: int
    organization: Optional[str]
    email: Optional[str]
    phone: Optional[str]


class InvoiceOut(BaseModel):
    invoice_id: str
    invoice_number: str
    description: str
    amount_due: float
    currency: str
    status: str
    issue_date: str
    due_date: str
    paid_at: Optional[str]


class NotificationOut(BaseModel):
    notification_id: str
    message: str
    type: str
    is_read: bool
    link: Optional[str]
    created_at: str


class InvoicesResponse(BaseModel):
    invoices: List[InvoiceOut]


class NotificationsResponse(BaseModel):
    notifications: List[NotificationOut]


@router.post("/create-order", response_model=CreateOrderResponse)
async def create_razorpay_order(request: Request, body: CreateOrderRequest):
    """
    Create a Razorpay order for a given invoice.
    """
    try:
        # Authenticate user
        user = decode_bwg_user(request)
        bwg_id = user["id"]
        
        # Get invoice details
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT invoice_id, amount_due, bwg_id, status 
                FROM invoices 
                WHERE invoice_id = %s AND bwg_id = %s AND status = %s
                """,
                (body.invoice_id, bwg_id, "UNPAID")
            )
            invoice = cur.fetchone()
            
            if not invoice:
                raise HTTPException(
                    status_code=404, 
                    detail="Invoice not found or already paid"
                )
            
            invoice_id, amount_due, _, _ = invoice
            
            # Get BWG user details for prefill
            cur.execute(
                """
                SELECT organization, email, phone 
                FROM bwg 
                WHERE id = %s
                """,
                (bwg_id,)
            )
            bwg_details = cur.fetchone()
            organization, email, phone = bwg_details if bwg_details else (None, None, None)
            
            # Create Razorpay order
            amount_in_paisa = int(float(amount_due) * 100)
            
            order_data = {
                "amount": amount_in_paisa,
                "currency": "INR",
                "receipt": invoice_id,
                "notes": {
                    "invoice_id": invoice_id,
                    "bwg_id": bwg_id,
                }
            }
            
            order = razorpay_client.order.create(data=order_data)
            
            # Store transaction record
            cur.execute(
                """
                INSERT INTO transactions 
                (invoice_id, razorpay_order_id, amount_paid, currency, status) 
                VALUES (%s, %s, %s, %s, %s)
                """,
                (invoice_id, order["id"], amount_due, "INR", "PENDING")
            )
            conn.commit()
            
            return CreateOrderResponse(
                order_id=order["id"],
                key=RAZORPAY_KEY_ID,
                amount=order["amount"],
                organization=organization,
                email=email,
                phone=phone
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating Razorpay order: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/invoices", response_model=InvoicesResponse)
async def list_invoices(request: Request):
    """Return all invoices for the authenticated BWG user."""
    user = decode_bwg_user(request)
    bwg_id = user["id"]

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT invoice_id, invoice_number, description, amount_due, currency,
                       status, issue_date, due_date, paid_at
                FROM invoices
                WHERE bwg_id = %s
                ORDER BY issue_date DESC
                """,
                (bwg_id,),
            )
            rows = cur.fetchall()

        invoices: List[InvoiceOut] = []
        for row in rows:
            amount_due = float(row[3]) if isinstance(row[3], Decimal) else row[3]
            invoices.append(
                InvoiceOut(
                    invoice_id=str(row[0]),
                    invoice_number=row[1],
                    description=row[2],
                    amount_due=amount_due,
                    currency=row[4],
                    status=row[5],
                    issue_date=row[6].isoformat() if row[6] else None,
                    due_date=row[7].isoformat() if row[7] else None,
                    paid_at=row[8].isoformat() if row[8] else None,
                )
            )

        return InvoicesResponse(invoices=invoices)

    except Exception as e:
        print(f"Error fetching invoices: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch invoices")


@router.get("/notifications", response_model=NotificationsResponse)
async def list_notifications(request: Request):
    """Return notifications for the authenticated BWG user."""
    user = decode_bwg_user(request)
    bwg_id = user["id"]

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT notification_id, message, type, is_read, link, created_at
                FROM notifications
                WHERE bwg_id = %s
                ORDER BY created_at DESC
                """,
                (bwg_id,),
            )
            rows = cur.fetchall()

        notifications: List[NotificationOut] = []
        for row in rows:
            notifications.append(
                NotificationOut(
                    notification_id=str(row[0]),
                    message=row[1],
                    type=row[2],
                    is_read=row[3],
                    link=row[4],
                    created_at=row[5].isoformat() if row[5] else None,
                )
            )

        return NotificationsResponse(notifications=notifications)

    except Exception as e:
        print(f"Error fetching notifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch notifications")


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/verify")
async def verify_and_capture_payment(payload: VerifyPaymentRequest):
    """Verify checkout signature and ensure capture, then mark invoice paid.

    This endpoint is intended to be called by the frontend after a successful
    Razorpay Checkout. It verifies the signature, captures the payment when
    required, and updates both `transactions` and `invoices` tables.
    """
    try:
        # 1) Verify signature using Razorpay utility
        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_order_id': payload.razorpay_order_id,
                'razorpay_payment_id': payload.razorpay_payment_id,
                'razorpay_signature': payload.razorpay_signature,
            })
        except razorpay.errors.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid payment signature")

        # 2) Check transaction and invoice from DB
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT t.invoice_id, i.amount_due
                FROM transactions t
                JOIN invoices i ON i.invoice_id = t.invoice_id
                WHERE t.razorpay_order_id = %s
                LIMIT 1
                """,
                (payload.razorpay_order_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Transaction not found for order")
            invoice_id, amount_due = row

            amount_in_paisa = int(float(amount_due) * 100)

            # 3) Fetch payment details from Razorpay
            payment = razorpay_client.payment.fetch(payload.razorpay_payment_id)

            # Normalize Razorpay status to our enum
            rp_status = payment.get('status')
            if rp_status == 'failed':
                # Record failure immediately
                with conn:
                    cur.execute(
                        """
                        UPDATE transactions
                        SET status = %s,
                            razorpay_payment_id = %s,
                            razorpay_signature = %s,
                            gateway_response = %s
                        WHERE razorpay_order_id = %s
                        """,
                        ("FAILED",
                         payload.razorpay_payment_id,
                         payload.razorpay_signature,
                         json.dumps(payment),
                         payload.razorpay_order_id)
                    )
                return {"status": "FAILED", "message": "Payment failed"}

            # 4) Capture when required (if not auto-captured)
            if rp_status == 'authorized':
                # Attempt capture; if capture fails, mark as FAILED
                try:
                    payment = razorpay_client.payment.capture(payload.razorpay_payment_id, amount_in_paisa)
                    rp_status = payment.get('status')
                except Exception as _cap_err:
                    with conn:
                        cur.execute(
                            """
                            UPDATE transactions
                            SET status = %s,
                                razorpay_payment_id = %s,
                                razorpay_signature = %s,
                                gateway_response = %s
                            WHERE razorpay_order_id = %s
                            """,
                            ("FAILED",
                             payload.razorpay_payment_id,
                             payload.razorpay_signature,
                             json.dumps({"error": "capture_failed"}),
                             payload.razorpay_order_id)
                        )
                    return {"status": "FAILED", "message": "Capture failed"}

            if rp_status != 'captured':
                # Mark as pending and let webhook update later
                with conn:
                    cur.execute(
                        """
                        UPDATE transactions
                        SET status = %s,
                            razorpay_payment_id = %s,
                            razorpay_signature = %s,
                            gateway_response = %s
                        WHERE razorpay_order_id = %s
                        """,
                        ("PENDING",
                         payload.razorpay_payment_id,
                         payload.razorpay_signature,
                         json.dumps(payment),
                         payload.razorpay_order_id)
                    )
                return {"status": "PENDING", "message": "Payment verified, awaiting capture"}

            # 5) Captured: mark paid
            with conn:
                cur.execute(
                    """
                    UPDATE transactions
                    SET status = %s,
                        razorpay_payment_id = %s,
                        razorpay_signature = %s,
                        gateway_response = %s
                    WHERE razorpay_order_id = %s
                    RETURNING invoice_id
                    """,
                    ("SUCCESSFUL",
                     payload.razorpay_payment_id,
                     payload.razorpay_signature,
                     json.dumps(payment),
                     payload.razorpay_order_id)
                )
                _ = cur.fetchone()

                cur.execute(
                    """
                    UPDATE invoices
                    SET status = %s,
                        paid_at = NOW()
                    WHERE invoice_id = %s
                    """,
                    ("PAID", invoice_id)
                )

        return {"status": "captured", "message": "Payment captured and recorded", "invoice_id": invoice_id}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Verify payment error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None)
):
    """
    Handle Razorpay webhook events for payment capture.
    """
    try:
        # Read raw body
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8")
        
        # Verify signature
        if not x_razorpay_signature or not RAZORPAY_WEBHOOK_SECRET:
            raise HTTPException(status_code=400, detail="Invalid signature or webhook secret not configured")
        
        expected_signature = hmac.new(
            RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()
        
        if expected_signature != x_razorpay_signature:
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Parse event
        event = json.loads(body_str)
        
        evt = event.get("event")
        # Handle payment.captured event
        if evt == "payment.captured":
            payment = event["payload"]["payment"]["entity"]
            order_id = payment["order_id"]
            payment_id = payment["id"]
            
            with get_db() as conn:
                cur = conn.cursor()
                
                # Start transaction
                cur.execute("BEGIN")
                
                try:
                    # Update transactions table
                    cur.execute(
                        """
                        UPDATE transactions 
                        SET status = %s,
                            razorpay_payment_id = %s,
                            razorpay_signature = %s,
                            gateway_response = %s
                        WHERE razorpay_order_id = %s
                        RETURNING invoice_id
                        """,
                        ("SUCCESSFUL", payment_id, x_razorpay_signature, 
                         json.dumps(payment), order_id)
                    )
                    
                    result = cur.fetchone()
                    if not result:
                        raise Exception("No matching transaction found for order_id")
                    
                    invoice_id = result[0]
                    
                    # Update invoices table
                    cur.execute(
                        """
                        UPDATE invoices
                        SET status = %s,
                            paid_at = NOW()
                        WHERE invoice_id = %s
                        """,
                        ("PAID", invoice_id)
                    )
                    
                    # Commit transaction
                    cur.execute("COMMIT")
                    
                except Exception as e:
                    cur.execute("ROLLBACK")
                    print(f"Webhook processing failed: {str(e)}")
                    raise HTTPException(
                        status_code=500, 
                        detail="Webhook processing failed"
                    )

        # Handle payment.failed event
        elif evt == "payment.failed":
            payment = event["payload"]["payment"]["entity"]
            order_id = payment.get("order_id")
            payment_id = payment.get("id")

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE transactions
                    SET status = %s,
                        razorpay_payment_id = %s,
                        razorpay_signature = %s,
                        gateway_response = %s
                    WHERE razorpay_order_id = %s
                    """,
                    ("FAILED", payment_id, x_razorpay_signature, json.dumps(payment), order_id)
                )
        
        return JSONResponse(content={"status": "ok"}, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


class TransactionOut(BaseModel):
    transaction_id: str
    invoice_id: str
    razorpay_order_id: Optional[str]
    razorpay_payment_id: Optional[str]
    status: str
    amount_paid: float
    currency: str
    paid_at: Optional[str]


class TransactionsResponse(BaseModel):
    transactions: List[TransactionOut]


@router.get("/transactions", response_model=TransactionsResponse)
async def list_transactions(request: Request, invoice_id: Optional[str] = None):
    """List transactions for the authenticated BWG user, optionally filtered by invoice."""
    user = decode_bwg_user(request)
    bwg_id = user["id"]

    try:
        with get_db() as conn:
            cur = conn.cursor()
            if invoice_id:
                cur.execute(
                    """
                    SELECT t.transaction_id, t.invoice_id, t.razorpay_order_id, t.razorpay_payment_id,
                           t.status, t.amount_paid, t.currency, t.paid_at
                    FROM transactions t
                    JOIN invoices i ON i.invoice_id = t.invoice_id
                    WHERE i.bwg_id = %s AND i.invoice_id = %s
                    ORDER BY t.paid_at DESC
                    """,
                    (bwg_id, invoice_id)
                )
            else:
                cur.execute(
                    """
                    SELECT t.transaction_id, t.invoice_id, t.razorpay_order_id, t.razorpay_payment_id,
                           t.status, t.amount_paid, t.currency, t.paid_at
                    FROM transactions t
                    JOIN invoices i ON i.invoice_id = t.invoice_id
                    WHERE i.bwg_id = %s
                    ORDER BY t.paid_at DESC
                    """,
                    (bwg_id,)
                )
            rows = cur.fetchall()

        txs: List[TransactionOut] = []
        for row in rows:
            amt = float(row[5]) if isinstance(row[5], Decimal) else row[5]
            txs.append(TransactionOut(
                transaction_id=str(row[0]),
                invoice_id=str(row[1]),
                razorpay_order_id=row[2],
                razorpay_payment_id=row[3],
                status=row[4],
                amount_paid=amt,
                currency=row[6],
                paid_at=row[7].isoformat() if row[7] else None
            ))

        return TransactionsResponse(transactions=txs)
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch transactions")


@router.post("/sweep-pending")
async def sweep_pending_abandoned(minutes: int = 30):
    """Mark long-pending transactions without a payment ID as FAILED.

    Intended to be triggered by a cron or admin task. This helps reflect
    cancellations/abandonment when users close checkout without completing.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE transactions t
                SET status = 'FAILED', gateway_response = COALESCE(gateway_response, '{}'::jsonb)
                WHERE t.status = 'PENDING'
                  AND (t.razorpay_payment_id IS NULL OR t.razorpay_payment_id = '')
                  AND (NOW() - t.paid_at) > (%s || ' minutes')::interval
                RETURNING t.transaction_id
                """,
                (str(minutes),)
            )
            updated = cur.fetchall()
            conn.commit()

        return {"updated": len(updated)}
    except Exception as e:
        print(f"Sweep pending error: {e}")
        raise HTTPException(status_code=500, detail="Sweep pending failed")


@router.post("/cancel")
async def cancel_order(order_id: str):
    """Explicitly mark a pending order as FAILED when user dismisses checkout."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE transactions
                SET status = 'FAILED'
                WHERE razorpay_order_id = %s
                  AND status = 'PENDING'
                  AND (razorpay_payment_id IS NULL OR razorpay_payment_id = '')
                RETURNING transaction_id
                """,
                (order_id,)
            )
            row = cur.fetchone()
            conn.commit()
        return {"updated": 1 if row else 0}
    except Exception as e:
        print(f"Cancel order error: {e}")
        raise HTTPException(status_code=500, detail="Cancel order failed")

@router.get("/test")
def payments_test():
    return {"message": "Payments router working"}
