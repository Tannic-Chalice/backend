# app/routers/admin/zones.py

from fastapi import APIRouter, HTTPException
from app.database import get_db

router = APIRouter()


@router.get("/zones")
def get_zones():
    try:
        with get_db() as conn:
            cur = conn.cursor()

            sql = """
                SELECT 
                    z.id AS zone_id,
                    z.name AS zone_name,
                    d.id AS division_id,
                    d.name AS division_name,
                    b.id AS bwg_id,
                    b.organization AS bwg_name,
                    b.address AS bwg_address,
                    dr.id AS driver_id,
                    dr.username AS driver_name,
                    dr.license_number AS license
                FROM zones z
                LEFT JOIN divisions d ON z.id = d.zone_id
                LEFT JOIN bwg b ON d.id = b.division_id
                LEFT JOIN driver dr ON d.id = dr.division_id
                ORDER BY z.id, d.id;
            """

            cur.execute(sql)
            rows = cur.fetchall()

        zones = []

        for row in rows:
            (
                zone_id,
                zone_name,
                division_id,
                division_name,
                bwg_id,
                bwg_name,
                bwg_address,
                driver_id,
                driver_name,
                license
            ) = row

            zone = next((z for z in zones if z["id"] == zone_id), None)
            if not zone:
                zone = {
                    "id": zone_id,
                    "name": zone_name,
                    "divisions": []
                }
                zones.append(zone)

            if division_id:
                division = next((d for d in zone["divisions"] if d["id"] == division_id), None)
                if not division:
                    division = {
                        "id": division_id,
                        "name": division_name or "",
                        "bwgs": [],
                        "drivers": []
                    }
                    zone["divisions"].append(division)

                if bwg_id and not any(b["id"] == bwg_id for b in division["bwgs"]):
                    division["bwgs"].append({
                        "id": bwg_id,
                        "name": bwg_name or "",
                        "address": bwg_address or ""
                    })

                if driver_id and not any(d["id"] == driver_id for d in division["drivers"]):
                    division["drivers"].append({
                        "id": driver_id,
                        "name": driver_name or "",
                        "license": license or ""
                    })

        return {"zones": zones}

    except Exception as e:
        print("Zones fetch error:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch zones data")
