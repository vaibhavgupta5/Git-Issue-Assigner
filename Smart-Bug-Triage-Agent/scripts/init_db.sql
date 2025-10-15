-- Initial database setup for Smart Bug Triage System
-- This script is run when the PostgreSQL container starts

-- Create extensions if they don't exist
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create database user if it doesn't exist (for development)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'smart_bug_triage') THEN
        CREATE ROLE smart_bug_triage WITH LOGIN PASSWORD 'smart_bug_triage';
    END IF;
END
$$;

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE smart_bug_triage TO smart_bug_triage;

-- Create schema for application tables
CREATE SCHEMA IF NOT EXISTS smart_bug_triage;
GRANT ALL ON SCHEMA smart_bug_triage TO smart_bug_triage;