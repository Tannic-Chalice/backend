-- Migration: Add Waste Quantity Calculation Columns to Pickups Table
-- Description: Adds columns to track calculated waste quantities with variation tracking
-- Date: 2024

-- Add new columns to pickups table
ALTER TABLE pickups
ADD COLUMN IF NOT EXISTS quantity_kg NUMERIC(12, 2),
ADD COLUMN IF NOT EXISTS variation_percent NUMERIC(5, 1),
ADD COLUMN IF NOT EXISTS is_missed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS carried_from_date DATE;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_pickups_bwg_date ON pickups(bwg_id, scheduled_date);
CREATE INDEX IF NOT EXISTS idx_pickups_missed ON pickups(is_missed) WHERE is_missed = true;
CREATE INDEX IF NOT EXISTS idx_pickups_quantity ON pickups(quantity_kg) WHERE quantity_kg IS NOT NULL;

-- Add comment to explain the columns
COMMENT ON COLUMN pickups.quantity_kg IS 'Calculated waste quantity for this pickup in kg';
COMMENT ON COLUMN pickups.variation_percent IS 'Variation from daily average (e.g., +7.8, -14.2)';
COMMENT ON COLUMN pickups.is_missed IS 'Was this pickup missed? true if missed, false if completed';
COMMENT ON COLUMN pickups.carried_from_date IS 'If missed=true, indicates which previous date waste is carried forward from';
