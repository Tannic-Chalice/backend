-- Add zone_id column with foreign key to vehicle_logs table
ALTER TABLE vehicle_logs 
ADD COLUMN zone_id INTEGER,
ADD CONSTRAINT vehicle_logs_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES zones(id);
