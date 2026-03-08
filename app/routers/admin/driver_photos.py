# Backend Router for Driver Photos with Approved BWG Filtering

from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor
import boto3
import os
from app.database import get_db
from typing import Optional

router = APIRouter()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")  # Fixed: was AWS_BUCKET_NAME

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)


def get_s3_presigned_url(s3_key: str, expiration: int = 3600) -> str:
    """Generate presigned URL for S3 object"""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        return None


@router.get("/driver-photos/bwg-list")
def get_bwgs_with_photo_counts():
    """
    Get list of BWGs that have uploaded photos, with photo counts.
    Returns BWGs grouped with their total photo count.
    """
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        dpp.bwg_id,
                        b.organization AS bwg_name,
                        b.address AS bwg_address,
                        b.zone AS bwg_zone,
                        b.ward_name AS bwg_ward,
                        b.status AS bwg_status,
                        COUNT(dpp.id) AS photo_count,
                        MAX(dpp.created_at) AS last_upload
                    FROM driver_pickup_photo dpp
                    LEFT JOIN bwg b ON dpp.bwg_id = b.id
                    GROUP BY dpp.bwg_id, b.organization, b.address, b.zone, b.ward_name, b.status
                    ORDER BY MAX(dpp.created_at) DESC
                """)
                bwgs = cur.fetchall()
        
        result = []
        for bwg in bwgs:
            result.append({
                "bwg_id": bwg['bwg_id'],
                "bwg_name": bwg['bwg_name'] or "Unknown BWG",
                "bwg_address": bwg['bwg_address'],
                "bwg_zone": bwg['bwg_zone'],
                "bwg_ward": bwg['bwg_ward'],
                "bwg_status": bwg['bwg_status'],
                "photo_count": bwg['photo_count'],
                "last_upload": bwg['last_upload'].isoformat() if bwg['last_upload'] else None,
            })
        
        return {
            "data": result,
            "total": len(result)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch BWG list: {str(e)}")


@router.get("/driver-photos")
def get_driver_photos_for_approved_bwgs(
    bwg_id: Optional[str] = None,
    driver_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    Fetch driver photos for approved BWGs with trip details.
    
    Returns photos from driver_pickup_photo table joined with:
    - bwg table (filtered for status = 'approved')
    - trips table (for trip details)
    - driver table (for driver info)
    """
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Build WHERE clause - Show all photos (remove approved filter for now)
                where_conditions = ["1=1"]  # Show all photos
                params = []
                
                if bwg_id:
                    where_conditions.append("dpp.bwg_id = %s")
                    params.append(bwg_id)
                
                if driver_id:
                    where_conditions.append("dpp.driver_id = %s")
                    params.append(driver_id)
                
                if date_from:
                    where_conditions.append("t.trip_date >= %s")
                    params.append(date_from)
                
                if date_to:
                    where_conditions.append("t.trip_date <= %s")
                    params.append(date_to)
                
                where_clause = " AND ".join(where_conditions)
                
                # Get total count
                count_query = f"""
                    SELECT COUNT(*) as total
                    FROM driver_pickup_photo dpp
                    LEFT JOIN bwg b ON dpp.bwg_id = b.id
                    LEFT JOIN trips t ON dpp.trip_id = t.trip_id
                    WHERE {where_clause}
                """
                cur.execute(count_query, params)
                total_count = cur.fetchone()['total']
                
                # Fetch photos with all details
                query = f"""
                    SELECT
                        dpp.id,
                        dpp.driver_id,
                        d.name AS driver_name,
                        d.phone_number AS driver_phone,
                        dpp.trip_id,
                        t.trip_date,
                        t.status AS trip_status,
                        v.registration_number AS vehicle_number,
                        dpp.bwg_id,
                        b.organization AS bwg_name,
                        b.address AS bwg_address,
                        b.zone AS bwg_zone,
                        b.ward_name AS bwg_ward,
                        dpp.s3_key,
                        dpp.created_at AS uploaded_at
                    FROM driver_pickup_photo dpp
                    LEFT JOIN bwg b ON dpp.bwg_id = b.id
                    LEFT JOIN driver d ON dpp.driver_id::text = d.id::text
                    LEFT JOIN trips t ON dpp.trip_id = t.trip_id
                    LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                    WHERE {where_clause}
                    ORDER BY dpp.created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                params.extend([limit, offset])
                cur.execute(query, params)
                photos = cur.fetchall()
        
        # Transform results
        result = []
        for photo in photos:
            presigned_url = get_s3_presigned_url(photo['s3_key']) if photo['s3_key'] else None
            result.append({
                "id": photo['id'],
                "driver_id": str(photo['driver_id']) if photo['driver_id'] else None,
                "driver_name": photo['driver_name'] or "Unknown Driver",
                "driver_phone": photo['driver_phone'],
                "trip_id": photo['trip_id'],
                "trip_date": photo['trip_date'].isoformat() if photo['trip_date'] else None,
                "trip_status": photo['trip_status'],
                "vehicle_number": photo['vehicle_number'],
                "bwg_id": photo['bwg_id'],
                "bwg_name": photo['bwg_name'] or "Unknown BWG",
                "bwg_address": photo['bwg_address'],
                "bwg_zone": photo['bwg_zone'],
                "bwg_ward": photo['bwg_ward'],
                "s3_key": photo['s3_key'],
                "photo_url": presigned_url,
                "uploaded_at": photo['uploaded_at'].isoformat() if photo['uploaded_at'] else None,
            })
        
        return {
            "data": result,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "count": len(result)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch driver photos: {str(e)}")


@router.get("/driver-photos/{photo_id}")
def get_driver_photo_detail(photo_id: int):
    """Get detailed information about a specific photo"""
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        dpp.id,
                        dpp.driver_id,
                        d.name AS driver_name,
                        d.phone_number AS driver_phone,
                        dpp.trip_id,
                        t.trip_date,
                        t.status AS trip_status,
                        v.registration_number AS vehicle_number,
                        dpp.bwg_id,
                        b.organization AS bwg_name,
                        b.address AS bwg_address,
                        b.zone AS bwg_zone,
                        b.ward_name AS bwg_ward,
                        b.status AS bwg_status,
                        dpp.s3_key,
                        dpp.created_at AS uploaded_at
                    FROM driver_pickup_photo dpp
                    INNER JOIN bwg b ON dpp.bwg_id = b.id
                    LEFT JOIN driver d ON dpp.driver_id = d.id
                    LEFT JOIN trips t ON dpp.trip_id = t.trip_id
                    LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                    WHERE dpp.id = %s AND b.status = 'approved'
                """, (photo_id,))
                photo = cur.fetchone()
        
        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")
        
        presigned_url = get_s3_presigned_url(photo['s3_key']) if photo['s3_key'] else None
        
        return {
            "id": photo['id'],
            "driver_id": str(photo['driver_id']) if photo['driver_id'] else None,
            "driver_name": photo['driver_name'],
            "driver_phone": photo['driver_phone'],
            "trip_id": photo['trip_id'],
            "trip_date": photo['trip_date'].isoformat() if photo['trip_date'] else None,
            "trip_status": photo['trip_status'],
            "vehicle_number": photo['vehicle_number'],
            "bwg_id": photo['bwg_id'],
            "bwg_name": photo['bwg_name'],
            "bwg_address": photo['bwg_address'],
            "bwg_zone": photo['bwg_zone'],
            "bwg_ward": photo['bwg_ward'],
            "photo_url": presigned_url,
            "uploaded_at": photo['uploaded_at'].isoformat() if photo['uploaded_at'] else None,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch photo: {str(e)}")
