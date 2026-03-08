-- Migration: Create table for storing pickup point prices for BWG payments
-- Run this migration to add the bwg_pickup_prices table

CREATE TABLE IF NOT EXISTS bwg_pickup_prices (
    id SERIAL PRIMARY KEY,
    bwg_id VARCHAR(10) NOT NULL,
    pickup_point_id VARCHAR(20) NOT NULL,  -- Can be BWG ID for main address or pickup_address ID (BWG001-P1)
    pickup_point_type VARCHAR(20) NOT NULL CHECK (pickup_point_type IN ('main', 'pickup')),
    price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (bwg_id, pickup_point_id)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_bwg_pickup_prices_bwg_id ON bwg_pickup_prices(bwg_id);

-- Comment for documentation
COMMENT ON TABLE bwg_pickup_prices IS 'Stores prices for each pickup point under a BWG for payment calculation';
