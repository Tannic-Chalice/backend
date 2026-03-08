"""
Scheduler for daily tasks

Handles:
- Daily regeneration of analytics with random variations at specified time
- Background scheduling using APScheduler
"""

from datetime import datetime, time, date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.daily_analytics_service import DailyAnalyticsGenerator, BwgCollectionReportGenerator
import logging
from app.database import get_db
from app.services.auto_billing_service import run_auto_billing
logger = logging.getLogger("uvicorn.error")

scheduler = None


def trigger_daily_tasks():
    """
    Trigger all daily tasks:
    - Daily analytics regeneration with ±25% variations
    - BWG collection report generation
    """
    logger.info("Triggering daily tasks...")
    try:
        mark_missed_pickups_end_of_day()
        # Generate daily analytics
        stats = DailyAnalyticsGenerator.regenerate_daily_analytics()
        logger.info(f"Daily analytics regenerated: {stats}")
        
        # Generate BWG collection reports
        bwg_stats = BwgCollectionReportGenerator.generate_collection_reports_for_date()
        logger.info(f"BWG collection reports generated: {bwg_stats}")
        
    except Exception as e:
        logger.error(f"Error in daily tasks: {e}")


def init_scheduler():
    """
    Initialize the background scheduler for daily tasks.
    Should be called once when the FastAPI app starts.
    """
    global scheduler
    
    try:
        scheduler = BackgroundScheduler(daemon=True)
        
        # Schedule daily tasks at 11:07 AM (11:07)
        # Includes: analytics regeneration + BWG collection reports
        scheduler.add_job(
            func=trigger_daily_tasks,
            trigger=CronTrigger(hour=23, minute=5),  # Run at 11:07 AM daily
            id='daily_tasks',
            name='Daily Tasks (Analytics + BWG Reports)',
            replace_existing=True,
            max_instances=1  # Only one instance should run
        )

        scheduler.add_job(
            func=trigger_auto_billing,
            trigger=CronTrigger(hour=0, minute=5),
            id="auto_billing_job",
            name="Automatic Billing",
            replace_existing=True,
            max_instances=1
        )
        
        scheduler.start()
        logger.info("Scheduler initialized and started. Daily tasks will run at 11:05 (11:05 AM)")
        
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {e}")
        raise


def shutdown_scheduler():
    """
    Shutdown the background scheduler when the app shuts down.
    """
    global scheduler
    
    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=True)
            logger.info("Scheduler shut down successfully")
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {e}")


def trigger_daily_analytics(target_date=None):
    """
    Manually trigger daily analytics generation and BWG collection reports.
    Useful for backfilling or immediate regeneration.
    
    Args:
        target_date: Specific date to generate data for (defaults to today)
    """
    try:
        stats = DailyAnalyticsGenerator.regenerate_daily_analytics(target_date)
        bwg_stats = BwgCollectionReportGenerator.generate_collection_reports_for_date(target_date)
        logger.info(f"Manual generation completed - Analytics: {stats}, BWG Reports: {bwg_stats}")
        return {'analytics': stats, 'bwg_reports': bwg_stats}
    except Exception as e:
        logger.error(f"Error in manual generation: {e}")
        raise

def mark_missed_pickups_end_of_day():
    """
    Mark all PENDING pickups as MISSED if their scheduled date has passed.
    Runs once daily (end of day).
    """
    logger.info("Marking missed pickups (end-of-day job)...")

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pickups
                    SET status = 'MISSED',
                        updated_at = NOW()
                    WHERE status = 'PENDING'
                      AND scheduled_date < CURRENT_DATE
                """)
                affected = cur.rowcount
                conn.commit()

        logger.info(f"Marked {affected} pickups as MISSED")

    except Exception as e:
        logger.error(f"Failed to mark missed pickups: {e}")

def trigger_auto_billing():
    """
    Scheduler-triggered auto billing
    """
    logger.info("Triggering auto billing from scheduler...")
    try:
        count = run_auto_billing(date.today())
        logger.info(f"Scheduler auto billing completed. Invoices generated: {count}")
    except Exception as e:
        logger.error(f"Scheduler auto billing failed: {e}", exc_info=True)