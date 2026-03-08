"""
Daily Processing Analytics Service

Handles:
- Generation of daily random variations within ±25% range
- Storage of variations for BWG wise, Vehicle wise, and Total processing reports
- Scheduled daily regeneration of variations
"""

from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
import random
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.database import get_db
from app.models import DailyProcessingAnalytics, Bwg, Vehicle, Pickup, Trip
import logging

logger = logging.getLogger("uvicorn.error")


class DailyAnalyticsGenerator:
    """
    Generate daily processing analytics with random variations.
    
    Logic:
    - Generate random variation between -25% and +25% for each metric
    - Variations are non-uniform randomization
    - Store in database for admin dashboard consumption
    - Regenerate fresh variations daily
    """
    
    VARIATION_MIN = -0.25  # -25%
    VARIATION_MAX = 0.25   # +25%
    
    @staticmethod
    def generate_random_variation() -> float:
        """
        Generate a random variation between -25% and +25%.
        
        Returns:
            float: Variation between -0.25 and 0.25 (non-uniform)
        """
        return random.uniform(DailyAnalyticsGenerator.VARIATION_MIN, DailyAnalyticsGenerator.VARIATION_MAX)
    
    @staticmethod
    def calculate_quantity_with_variation(base_quantity: float, variation_percent: float) -> float:
        """
        Calculate actual quantity by applying variation percentage to base.
        
        Args:
            base_quantity: Base quantity in kg
            variation_percent: Variation percentage (-25 to +25)
            
        Returns:
            float: Calculated quantity (base_quantity * (1 + variation_percent/100))
        """
        if base_quantity is None or base_quantity <= 0:
            return 0.0
        
        multiplier = 1 + (variation_percent / 100.0)
        calculated_qty = base_quantity * multiplier
        return round(max(0, calculated_qty), 2)
    
    @staticmethod
    def generate_daily_analytics_for_bwg(
        bwg_id: str,
        target_date: date,
        db: Session
    ) -> Optional[DailyProcessingAnalytics]:
        """
        Generate daily analytics for a specific BWG on a given date.
        
        Args:
            bwg_id: BWG identifier
            target_date: Date for which to generate analytics
            db: Database session
            
        Returns:
            DailyProcessingAnalytics object or None if BWG not found
        """
        try:
            # Get BWG details
            bwg = db.query(Bwg).filter(Bwg.id == bwg_id).first()
            if not bwg or not bwg.daily_waste_kg:
                logger.warning(f"BWG {bwg_id} not found or has no daily_waste_kg set")
                return None
            
            base_quantity = float(bwg.daily_waste_kg)
            
            # Generate random variations
            bwg_variation = DailyAnalyticsGenerator.generate_random_variation()
            vehicle_variation = DailyAnalyticsGenerator.generate_random_variation()
            total_variation = DailyAnalyticsGenerator.generate_random_variation()
            
            # Convert to percentages
            bwg_variation_percent = round(bwg_variation * 100, 1)
            vehicle_variation_percent = round(vehicle_variation * 100, 1)
            total_variation_percent = round(total_variation * 100, 1)
            
            # Calculate quantities
            bwg_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, bwg_variation_percent
            )
            vehicle_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, vehicle_variation_percent
            )
            total_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, total_variation_percent
            )
            
            # Create or update analytics record
            analytics = db.query(DailyProcessingAnalytics).filter(
                and_(
                    DailyProcessingAnalytics.date == target_date,
                    DailyProcessingAnalytics.bwg_id == bwg_id,
                    DailyProcessingAnalytics.vehicle_id.is_(None)
                )
            ).first()
            
            if not analytics:
                analytics = DailyProcessingAnalytics(
                    date=target_date,
                    bwg_id=bwg_id
                )
                db.add(analytics)
            
            analytics.bwg_wise_variation_percent = bwg_variation_percent
            analytics.vehicle_wise_variation_percent = vehicle_variation_percent
            analytics.total_processing_variation_percent = total_variation_percent
            analytics.bwg_wise_quantity_kg = bwg_quantity
            analytics.vehicle_wise_quantity_kg = vehicle_quantity
            analytics.total_processing_quantity_kg = total_quantity
            analytics.updated_at = datetime.now()
            
            db.commit()
            logger.info(f"Generated analytics for BWG {bwg_id} on {target_date}")
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error generating analytics for BWG {bwg_id}: {e}")
            db.rollback()
            return None
    
    @staticmethod
    def generate_daily_analytics_for_vehicle(
        vehicle_id: int,
        target_date: date,
        db: Session
    ) -> Optional[DailyProcessingAnalytics]:
        """
        Generate daily analytics for a specific vehicle on a given date.
        
        Args:
            vehicle_id: Vehicle identifier
            target_date: Date for which to generate analytics
            db: Database session
            
        Returns:
            DailyProcessingAnalytics object or None if vehicle not found
        """
        try:
            # Get vehicle details
            vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
            if not vehicle:
                logger.warning(f"Vehicle {vehicle_id} not found")
                return None
            
            # Get average daily waste from associated BWGs
            pickups = db.query(func.avg(Pickup.quantity_kg)).filter(
                and_(
                    Pickup.trip_id.in_(
                        db.query(Trip.trip_id).filter(Trip.vehicle_id == vehicle_id)
                    ),
                    Pickup.scheduled_date == target_date
                )
            ).scalar()
            
            base_quantity = float(pickups) if pickups else 50.0  # Default 50 kg if no data
            
            # Generate random variations
            bwg_variation = DailyAnalyticsGenerator.generate_random_variation()
            vehicle_variation = DailyAnalyticsGenerator.generate_random_variation()
            total_variation = DailyAnalyticsGenerator.generate_random_variation()
            
            # Convert to percentages
            bwg_variation_percent = round(bwg_variation * 100, 1)
            vehicle_variation_percent = round(vehicle_variation * 100, 1)
            total_variation_percent = round(total_variation * 100, 1)
            
            # Calculate quantities
            bwg_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, bwg_variation_percent
            )
            vehicle_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, vehicle_variation_percent
            )
            total_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, total_variation_percent
            )
            
            # Create or update analytics record
            analytics = db.query(DailyProcessingAnalytics).filter(
                and_(
                    DailyProcessingAnalytics.date == target_date,
                    DailyProcessingAnalytics.vehicle_id == vehicle_id
                )
            ).first()
            
            if not analytics:
                analytics = DailyProcessingAnalytics(
                    date=target_date,
                    vehicle_id=vehicle_id
                )
                db.add(analytics)
            
            analytics.bwg_wise_variation_percent = bwg_variation_percent
            analytics.vehicle_wise_variation_percent = vehicle_variation_percent
            analytics.total_processing_variation_percent = total_variation_percent
            analytics.bwg_wise_quantity_kg = bwg_quantity
            analytics.vehicle_wise_quantity_kg = vehicle_quantity
            analytics.total_processing_quantity_kg = total_quantity
            analytics.updated_at = datetime.now()
            
            db.commit()
            logger.info(f"Generated analytics for Vehicle {vehicle_id} on {target_date}")
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error generating analytics for Vehicle {vehicle_id}: {e}")
            db.rollback()
            return None
    
    @staticmethod
    def generate_total_processing_analytics(
        target_date: date,
        db: Session
    ) -> Optional[DailyProcessingAnalytics]:
        """
        Generate daily analytics for total processing on a given date.
        
        Args:
            target_date: Date for which to generate analytics
            db: Database session
            
        Returns:
            DailyProcessingAnalytics object
        """
        try:
            # Get total daily pickups
            total_quantity = db.query(func.sum(Pickup.quantity_kg)).filter(
                Pickup.scheduled_date == target_date
            ).scalar()
            
            base_quantity = float(total_quantity) if total_quantity else 0.0
            
            # Generate random variations
            bwg_variation = DailyAnalyticsGenerator.generate_random_variation()
            vehicle_variation = DailyAnalyticsGenerator.generate_random_variation()
            total_variation = DailyAnalyticsGenerator.generate_random_variation()
            
            # Convert to percentages
            bwg_variation_percent = round(bwg_variation * 100, 1)
            vehicle_variation_percent = round(vehicle_variation * 100, 1)
            total_variation_percent = round(total_variation * 100, 1)
            
            # Calculate quantities
            bwg_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, bwg_variation_percent
            )
            vehicle_quantity = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, vehicle_variation_percent
            )
            total_quantity_calc = DailyAnalyticsGenerator.calculate_quantity_with_variation(
                base_quantity, total_variation_percent
            )
            
            # Create or update total processing analytics record (no bwg_id or vehicle_id)
            analytics = db.query(DailyProcessingAnalytics).filter(
                and_(
                    DailyProcessingAnalytics.date == target_date,
                    DailyProcessingAnalytics.bwg_id.is_(None),
                    DailyProcessingAnalytics.vehicle_id.is_(None)
                )
            ).first()
            
            if not analytics:
                analytics = DailyProcessingAnalytics(date=target_date)
                db.add(analytics)
            
            analytics.bwg_wise_variation_percent = bwg_variation_percent
            analytics.vehicle_wise_variation_percent = vehicle_variation_percent
            analytics.total_processing_variation_percent = total_variation_percent
            analytics.bwg_wise_quantity_kg = bwg_quantity
            analytics.vehicle_wise_quantity_kg = vehicle_quantity
            analytics.total_processing_quantity_kg = total_quantity_calc
            analytics.updated_at = datetime.now()
            
            db.commit()
            logger.info(f"Generated total processing analytics for {target_date}")
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error generating total processing analytics: {e}")
            db.rollback()
            return None
    
    @staticmethod
    def regenerate_daily_analytics(target_date: Optional[date] = None) -> Dict[str, int]:
        """
        Regenerate all daily analytics for a specific date or today.
        
        Args:
            target_date: Date to regenerate analytics for (defaults to today)
            
        Returns:
            Dictionary with counts: {
                'bwg_count': int,
                'vehicle_count': int,
                'total_processing': int
            }
        """
        target_date = target_date or date.today()
        stats = {
            'bwg_count': 0,
            'vehicle_count': 0,
            'total_processing': 0
        }
        
        try:
            from app.database import SessionLocal
            
            db = SessionLocal()
            try:
                # Get all active BWGs
                bwgs = db.query(Bwg).filter(Bwg.status == 'approved').all()
                for bwg in bwgs:
                    if DailyAnalyticsGenerator.generate_daily_analytics_for_bwg(bwg.id, target_date, db):
                        stats['bwg_count'] += 1
                
                # Get all active vehicles
                vehicles = db.query(Vehicle).filter(Vehicle.vehicle_id.isnot(None)).all()
                for vehicle in vehicles:
                    if DailyAnalyticsGenerator.generate_daily_analytics_for_vehicle(vehicle.vehicle_id, target_date, db):
                        stats['vehicle_count'] += 1
                
                # Generate total processing analytics
                if DailyAnalyticsGenerator.generate_total_processing_analytics(target_date, db):
                    stats['total_processing'] += 1
                
                logger.info(f"Daily analytics regenerated for {target_date}: {stats}")
                
            except Exception as e:
                logger.error(f"Error in regenerate_daily_analytics: {e}")
                db.rollback()
                raise
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in regenerate_daily_analytics: {e}")
        
        return stats


def get_daily_analytics_generator() -> DailyAnalyticsGenerator:
    """
    Factory function to get DailyAnalyticsGenerator instance.
    
    Returns:
        DailyAnalyticsGenerator instance
    """
    return DailyAnalyticsGenerator()


class BwgCollectionReportGenerator:
    """
    Generate daily BWG collection reports with ±25% waste variation.
    
    Creates one report per BWG per day with:
    - Random waste quantity within ±25% of daily_waste_kg
    - Wet/dry waste split based on BWG configuration
    - Ward and zone information
    """
    
    VARIATION_MIN = -0.25  # -25%
    VARIATION_MAX = 0.25   # +25%
    
    @staticmethod
    def generate_random_variation() -> float:
        """Generate random variation between -25% and +25%."""
        return random.uniform(BwgCollectionReportGenerator.VARIATION_MIN, BwgCollectionReportGenerator.VARIATION_MAX)
    
    @staticmethod
    def generate_collection_reports_for_date(target_date: Optional[date] = None) -> Dict[str, int]:
        """
        Generate collection reports for all BWGs on a specific date.
        
        Args:
            target_date: Date to generate reports for (defaults to today)
            
        Returns:
            Dictionary with count of generated reports: {'created': int, 'updated': int}
        """
        target_date = target_date or date.today()
        stats = {'created': 0, 'updated': 0}
        
        try:
            from app.database import SessionLocal
            from app.models import BwgCollectionReport
            
            db = SessionLocal()
            
            try:
                # Get all approved BWGs with daily_waste_kg set
                try:
                    bwgs = db.query(Bwg).filter(
                        and_(
                            Bwg.status == 'approved',
                            Bwg.daily_waste_kg.isnot(None),
                            Bwg.daily_waste_kg > 0
                        )
                    ).all()
                except Exception as query_error:
                    logger.warning(f"Error querying BWGs, trying alternative: {query_error}")
                    # Fallback: try a simpler query
                    bwgs = db.query(Bwg).filter(Bwg.status == 'approved').all()
                    bwgs = [b for b in bwgs if b.daily_waste_kg and float(b.daily_waste_kg) > 0]
                
                logger.info(f"Found {len(bwgs)} approved BWGs for collection report generation")
                
                for bwg in bwgs:
                    try:
                        # Generate random variation
                        variation = BwgCollectionReportGenerator.generate_random_variation()
                        
                        # Calculate base waste
                        base_waste = float(bwg.daily_waste_kg)
                        total_waste = base_waste * (1 + variation)
                        
                        # Calculate wet and dry waste
                        # Default: 60% wet, 40% dry (from waste processing standards)
                        wet_waste = total_waste * 0.60
                        dry_waste = total_waste * 0.40
                        
                        # Use BWG's configured wet/dry if available
                        if hasattr(bwg, 'wet_waste_kg') and hasattr(bwg, 'dry_waste_kg'):
                            if bwg.wet_waste_kg and bwg.dry_waste_kg:
                                try:
                                    total_configured = float(bwg.wet_waste_kg) + float(bwg.dry_waste_kg)
                                    if total_configured > 0:
                                        wet_ratio = float(bwg.wet_waste_kg) / total_configured
                                        wet_waste = total_waste * wet_ratio
                                        dry_waste = total_waste * (1 - wet_ratio)
                                except (ValueError, TypeError):
                                    pass  # Use defaults if calculation fails
                        
                        # Check if report already exists for this date
                        existing = db.query(BwgCollectionReport).filter(
                            and_(
                                BwgCollectionReport.bwg_id == bwg.id,
                                BwgCollectionReport.date == target_date
                            )
                        ).first()
                        
                        if existing:
                            # Update existing report
                            existing.wet_waste_kg = round(wet_waste, 2)
                            existing.dry_waste_kg = round(dry_waste, 2)
                            existing.bwg_name = bwg.organization or bwg.person
                            existing.corporation = bwg.zone or "Central"  # Zone acts as corporation/GBA
                            existing.ward_info = f"{bwg.ward_number} - {bwg.ward_name}" if bwg.ward_number else bwg.ward_name or ""
                            existing.updated_at = datetime.now()
                            stats['updated'] += 1
                            logger.info(f"Updated collection report for BWG {bwg.id} on {target_date}")
                        else:
                            # Create new report
                            report = BwgCollectionReport(
                                bwg_id=bwg.id,
                                bwg_name=bwg.organization or bwg.person,
                                date=target_date,
                                corporation=bwg.zone or "Central",  # Zone acts as corporation/GBA
                                ward_info=f"{bwg.ward_number} - {bwg.ward_name}" if bwg.ward_number else bwg.ward_name or "",
                                wet_waste_kg=round(wet_waste, 2),
                                dry_waste_kg=round(dry_waste, 2),
                                vehicle_no=None,  # TODO: Link to actual assigned vehicle
                                created_at=datetime.now(),
                                updated_at=datetime.now()
                            )
                            db.add(report)
                            stats['created'] += 1
                            logger.info(f"Created collection report for BWG {bwg.id} on {target_date}")
                    
                    except Exception as e:
                        logger.error(f"Error generating report for BWG {bwg.id}: {e}")
                        continue
                
                db.commit()
                logger.info(f"BWG collection reports generated for {target_date}: {stats}")
                
            except Exception as e:
                logger.error(f"Error in generate_collection_reports: {e}")
                db.rollback()
                raise
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Error in BwgCollectionReportGenerator: {e}")
        
        return stats


def get_bwg_collection_report_generator() -> BwgCollectionReportGenerator:
    """
    Factory function to get BwgCollectionReportGenerator instance.
    
    Returns:
        BwgCollectionReportGenerator instance
    """
    return BwgCollectionReportGenerator()
