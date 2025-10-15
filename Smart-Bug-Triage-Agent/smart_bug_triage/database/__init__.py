"""Database connection and management utilities."""

from .connection import (
    DatabaseManager,
    get_db_session,
    init_database,
    get_database_manager,
    DatabaseError,
    ConnectionError,
    SessionError,
    handle_db_exceptions,
    execute_query,
    execute_update
)

from .migrations import (
    MigrationManager,
    Migration,
    run_migrations,
    rollback_migrations,
    check_migration_status,
    get_all_migrations
)

__all__ = [
    # Connection management
    'DatabaseManager',
    'get_db_session',
    'init_database',
    'get_database_manager',
    
    # Exceptions
    'DatabaseError',
    'ConnectionError',
    'SessionError',
    
    # Utilities
    'handle_db_exceptions',
    'execute_query',
    'execute_update',
    
    # Migrations
    'MigrationManager',
    'Migration',
    'run_migrations',
    'rollback_migrations',
    'check_migration_status',
    'get_all_migrations'
]