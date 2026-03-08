"""
BSWML Dashboard API Endpoints

Provides metrics and client data for the BSWML dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from app.database import get_db
import logging

router = APIRouter(prefix="/bswl", tags=["BSWML Dashboard"])
logger = logging.getLogger("uvicorn.error")


@router.get("/dashboard-metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """
    Get today and month-to-date waste metrics.
    
    Returns metrics for:
    - Wet Waste Collected
    - Dry Waste Collected
    - Compost Production
    - Completed Pickups
    """
    try:
        today = date.today()
        month_start = date(today.year, today.month, 1)

        # Import models here to avoid circular imports
        from app.models import Pickup
        
        # Query pickups for today
        today_pickups = db.query(Pickup).filter(
            Pickup.scheduled_date == today,
            Pickup.status == "DONE"
        ).count()

        # Query pickups for month-to-date
        mtd_pickups = db.query(Pickup).filter(
            Pickup.scheduled_date >= month_start,
            Pickup.scheduled_date <= today,
            Pickup.status == "DONE"
        ).count()

        # For now, return sample data
        # In production, calculate from weight_bridge table
        today_total_weight = 270.5  # Sample data
        mtd_total_weight = 6091.25  # Sample data

        return {
            "wet_waste_collected": {
                "today": round(today_total_weight * 0.60, 2),
                "mtd": round(mtd_total_weight * 0.60, 2)
            },
            "dry_waste_collected": {
                "today": round(today_total_weight * 0.40, 2),
                "mtd": round(mtd_total_weight * 0.40, 2)
            },
            "compost_production": {
                "today": round(today_total_weight * 0.60 * 0.30, 2),
                "mtd": round(mtd_total_weight * 0.60 * 0.30, 2)
            },
            "completed_pickups": {
                "today": today_pickups,
                "mtd": mtd_pickups
            }
        }

    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients")
def get_bwg_clients(db: Session = Depends(get_db)):
    """
    Get list of all BWG clients with waste and pricing data.
    
    Returns array of clients with:
    - BWG details
    - Waste quantities (wet, dry, total)
    - Pricing information
    """
    try:
        # Sample data for testing
        # In production, query from bwg, weight_bridge, and billing_contracts tables
        
        sample_clients = [
            {
                "id": "BWG001",
                "bwg_name": "East Zone Waste Processing",
                "bwg_id": "BWG001",
                "corporation": "GBA Corporation",
                "ward_number": "101",
                "ward_name": "Downtown Ward",
                "wet_waste_qty": 250.5,
                "dry_waste_qty": 180.3,
                "total_waste_qty": 430.8,
                "price_per_kg": 8.50
            },
            {
                "id": "BWG002",
                "bwg_name": "West Hub Processing",
                "bwg_id": "BWG002",
                "corporation": "GBA Corporation",
                "ward_number": "102",
                "ward_name": "Commercial Ward",
                "wet_waste_qty": 180.0,
                "dry_waste_qty": 140.5,
                "total_waste_qty": 320.5,
                "price_per_kg": 8.75
            },
            {
                "id": "BWG003",
                "bwg_name": "South Center Facility",
                "bwg_id": "BWG003",
                "corporation": "GBA Corporation",
                "ward_number": "103",
                "ward_name": "Residential Ward",
                "wet_waste_qty": 220.0,
                "dry_waste_qty": 165.0,
                "total_waste_qty": 385.0,
                "price_per_kg": 8.50
            },
            {
                "id": "BWG004",
                "bwg_name": "North Facility Hub",
                "bwg_id": "BWG004",
                "corporation": "GBA Corporation",
                "ward_number": "104",
                "ward_name": "Industrial Ward",
                "wet_waste_qty": 195.5,
                "dry_waste_qty": 150.0,
                "total_waste_qty": 345.5,
                "price_per_kg": 8.65
            },
            {
                "id": "BWG005",
                "bwg_name": "Central Hub Processing",
                "bwg_id": "BWG005",
                "corporation": "GBA Corporation",
                "ward_number": "105",
                "ward_name": "Downtown Extension",
                "wet_waste_qty": 275.0,
                "dry_waste_qty": 210.5,
                "total_waste_qty": 485.5,
                "price_per_kg": 9.00
            },
            {
                "id": "BWG006",
                "bwg_name": "East Extension Waste",
                "bwg_id": "BWG006",
                "corporation": "GBA Corporation",
                "ward_number": "106",
                "ward_name": "East Extension",
                "wet_waste_qty": 210.0,
                "dry_waste_qty": 160.0,
                "total_waste_qty": 370.0,
                "price_per_kg": 8.50
            },
            {
                "id": "BWG007",
                "bwg_name": "West Extension Center",
                "bwg_id": "BWG007",
                "corporation": "GBA Corporation",
                "ward_number": "107",
                "ward_name": "West Extension",
                "wet_waste_qty": 230.5,
                "dry_waste_qty": 175.0,
                "total_waste_qty": 405.5,
                "price_per_kg": 8.60
            },
            {
                "id": "BWG008",
                "bwg_name": "South Extension Hub",
                "bwg_id": "BWG008",
                "corporation": "GBA Corporation",
                "ward_number": "108",
                "ward_name": "South Extension",
                "wet_waste_qty": 265.0,
                "dry_waste_qty": 195.0,
                "total_waste_qty": 460.0,
                "price_per_kg": 8.75
            },
        ]

        return sample_clients

    except Exception as e:
        logger.error(f"Error fetching BWG clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))
