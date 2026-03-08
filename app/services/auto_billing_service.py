from datetime import date
from dateutil.relativedelta import relativedelta
import uuid
import logging

from app.database import get_db

logger = logging.getLogger("uvicorn.error")


def run_auto_billing(target_date: date | None = None):
    """
    Core auto-billing logic.
    Can be called by:
    - API
    - Scheduler
    - Manual admin trigger
    """
    billing_date = target_date or date.today()
    generated_count = 0

    logger.info(f"Running auto billing for date: {billing_date}")

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                contract_id,
                bwg_id,
                default_amount,
                invoice_counter
            FROM billing_contracts
            WHERE status = 'ACTIVE'
              AND next_invoice_date <= %s
        """, (billing_date,))

        contracts = cur.fetchall()

        for contract_id, bwg_id, amount, invoice_counter in contracts:
            invoice_counter = invoice_counter or 0
            new_counter = invoice_counter + 1

            # Idempotency check
            cur.execute("""
                SELECT 1 FROM invoices
                WHERE contract_id = %s AND issue_date = %s
            """, (contract_id, billing_date))

            if cur.fetchone():
                logger.warning(f"Invoice already exists for {bwg_id} on {billing_date}")
                continue

            invoice_id = str(uuid.uuid4())
            invoice_number = f"INV-{bwg_id}-{new_counter}"
            due_date = billing_date + relativedelta(days=15)

            cur.execute("""
                INSERT INTO invoices (
                    invoice_id, bwg_id, contract_id,
                    invoice_number, description,
                    amount_due, currency, status,
                    issue_date, due_date,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'INR',
                        'UNPAID', %s, %s, NOW(), NOW())
            """, (
                invoice_id,
                bwg_id,
                contract_id,
                invoice_number,
                f"Auto Invoice - {billing_date.strftime('%B %Y')}",
                amount,
                billing_date,
                due_date
            ))

            cur.execute("""
                UPDATE billing_contracts
                SET
                    invoice_counter = %s,
                    next_invoice_date = next_invoice_date + INTERVAL '1 month',
                    updated_at = NOW()
                WHERE contract_id = %s
            """, (new_counter, contract_id))

            generated_count += 1

        conn.commit()

    logger.info(f"Auto billing completed. Generated invoices: {generated_count}")
    return generated_count
