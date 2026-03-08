-- Migration: Add daily_processing_analytics table for random variations
-- Purpose: Store daily random variations within ±25% for BWG wise, Vehicle wise, and Total processing
-- This table is used by the admin dashboard for analytics reports

CREATE TABLE IF NOT EXISTS daily_processing_analytics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    bwg_id VARCHAR(10) REFERENCES bwg(id) ON DELETE CASCADE,
    vehicle_id INTEGER REFERENCES vehicles(vehicle_id) ON DELETE CASCADE,
    
    -- Random variation percentages (±25%)
    bwg_wise_variation_percent NUMERIC(5, 1),
    vehicle_wise_variation_percent NUMERIC(5, 1),
    total_processing_variation_percent NUMERIC(5, 1),
    
    -- Calculated quantities (base * (1 + variation%))
    bwg_wise_quantity_kg NUMERIC(12, 2),
    vehicle_wise_quantity_kg NUMERIC(12, 2),
    total_processing_quantity_kg NUMERIC(12, 2),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Indices for faster querying
    UNIQUE(date, bwg_id, vehicle_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_analytics_date ON daily_processing_analytics(date);
CREATE INDEX IF NOT EXISTS idx_daily_analytics_bwg_id ON daily_processing_analytics(bwg_id);
CREATE INDEX IF NOT EXISTS idx_daily_analytics_vehicle_id ON daily_processing_analytics(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_daily_analytics_date_bwg ON daily_processing_analytics(date, bwg_id);
CREATE INDEX IF NOT EXISTS idx_daily_analytics_date_vehicle ON daily_processing_analytics(date, vehicle_id);
