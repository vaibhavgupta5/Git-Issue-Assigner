#!/usr/bin/env python
"""
Initialize the Smart Bug Triage database.
Run this script to set up the database schema and run migrations.
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from smart_bug_triage.database.connection import DatabaseManager
from smart_bug_triage.database.migrations import run_migrations, check_migration_status
from smart_bug_triage.config.settings import SystemConfig


def check_database_exists(config):
    """Check if the database exists, create if it doesn't."""
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    
    try:
        # Connect to PostgreSQL server (not specific database)
        conn = psycopg2.connect(
            host=config.database.host,
            port=config.database.port,
            user=config.database.username,
            password=config.database.password,
            database='postgres'  # Connect to default postgres database
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (config.database.database,)
        )
        
        if not cursor.fetchone():
            print(f"📦 Creating database '{config.database.database}'...")
            cursor.execute(f'CREATE DATABASE "{config.database.database}"')
            print("✅ Database created successfully!")
        else:
            print(f"📦 Database '{config.database.database}' already exists")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking/creating database: {e}")
        return False


def main():
    """Initialize the database with required tables and run migrations."""
    print("🚀 Smart Bug Triage Database Initialization")
    print("=" * 50)
    
    # Load configuration
    print("📋 Loading configuration...")
    config = SystemConfig.from_env()
    
    # Show configuration (without sensitive data)
    print(f"🔗 Database: {config.database.host}:{config.database.port}/{config.database.database}")
    print(f"👤 User: {config.database.username}")
    
    # Validate configuration (skip GitHub token requirement for DB setup)
    print("🔍 Validating configuration...")
    if not config.database.host or not config.database.database:
        print("❌ Database configuration is incomplete!")
        print("Required environment variables:")
        print("  - DB_HOST (or use default 'localhost')")
        print("  - DB_NAME (or use default 'smart_bug_triage')")
        print("  - DB_USERNAME (or use default 'postgres')")
        print("  - DB_PASSWORD")
        return False
    
    # Check if database exists, create if needed
    print("🔍 Checking database existence...")
    if not check_database_exists(config):
        return False
    
    try:
        # Initialize database manager
        print("🔧 Initializing database connection...")
        db_url = f"postgresql://{config.database.username}:{config.database.password}@{config.database.host}:{config.database.port}/{config.database.database}"
        db_manager = DatabaseManager(db_url)
        db_manager.initialize()
        
        # Test connection
        print("🏥 Testing database connection...")
        if not db_manager.health_check():
            print("❌ Database connection failed!")
            return False
        print("✅ Database connection successful!")
        
        # Check current migration status
        print("📊 Checking migration status...")
        status = check_migration_status(db_manager)
        print(f"📈 Applied migrations: {len(status['applied_migrations'])}")
        print(f"⏳ Pending migrations: {len(status['pending_migrations'])}")
        
        if status['pending_migrations']:
            print("🔄 Running database migrations...")
            run_migrations(db_manager)
            print("✅ All migrations applied successfully!")
        else:
            print("✅ Database is up to date!")
        
        # Final health check
        print("🏥 Final health check...")
        if db_manager.health_check():
            print("🎉 Database initialization completed successfully!")
            print("\n📋 Summary:")
            print(f"  ✅ Database: {config.database.database}")
            print(f"  ✅ Host: {config.database.host}:{config.database.port}")
            print(f"  ✅ Tables: Created with migrations")
            print(f"  ✅ Indexes: Applied for performance")
            print("\n🚀 You can now run the Triage Agent!")
            return True
        else:
            print("❌ Final health check failed!")
            return False
            
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Make sure PostgreSQL is running:")
        print("   brew services start postgresql")
        print("2. Check your database credentials")
        print("3. Ensure the database user has CREATE privileges")
        return False
    finally:
        if 'db_manager' in locals():
            db_manager.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)