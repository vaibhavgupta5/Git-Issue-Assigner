"""Database connection and session management utilities."""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, Engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError

from ..models.database import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager with connection URL."""
        self.database_url = database_url or self._get_database_url()
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._initialized = False
    
    def _get_database_url(self) -> str:
        """Get database URL from environment variables."""
        # Try different environment variable names
        url = (
            os.getenv('DATABASE_URL') or
            os.getenv('DB_URL') or
            os.getenv('POSTGRES_URL')
        )
        
        if not url:
            # Default to local PostgreSQL for development
            host = os.getenv('DB_HOST', 'localhost')
            port = os.getenv('DB_PORT', '5432')
            name = os.getenv('DB_NAME', 'smart_bug_triage')
            user = os.getenv('DB_USER', 'postgres')
            password = os.getenv('DB_PASSWORD', 'postgres')
            
            url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        
        return url
    
    def initialize(self) -> None:
        """Initialize database engine and session factory."""
        if self._initialized:
            return
        
        try:
            # Create engine with connection pooling
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=3600,   # Recycle connections every hour
                echo=os.getenv('DB_ECHO', 'false').lower() == 'true'
            )
            
            # Add connection event listeners for better error handling
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                """Set connection parameters if needed."""
                pass
            
            @event.listens_for(self.engine, "checkout")
            def receive_checkout(dbapi_connection, connection_record, connection_proxy):
                """Log connection checkout for debugging."""
                logger.debug("Connection checked out from pool")
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            self._initialized = True
            logger.info("Database manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def create_tables(self) -> None:
        """Create all database tables."""
        if not self._initialized:
            self.initialize()
        
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def drop_tables(self) -> None:
        """Drop all database tables (use with caution)."""
        if not self._initialized:
            self.initialize()
        
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.info("Database tables dropped successfully")
        except Exception as e:
            logger.error(f"Failed to drop database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup."""
        if not self._initialized:
            self.initialize()
        
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def get_session_factory(self) -> sessionmaker:
        """Get the session factory for manual session management."""
        if not self._initialized:
            self.initialize()
        return self.SessionLocal
    
    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            with self.get_session() as session:
                from sqlalchemy import text
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def close(self) -> None:
        """Close database connections and cleanup."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


def get_db_session() -> Generator[Session, None, None]:
    """Dependency function for getting database sessions."""
    with db_manager.get_session() as session:
        yield session


def init_database(database_url: Optional[str] = None) -> None:
    """Initialize the database with optional custom URL."""
    global db_manager
    if database_url:
        db_manager = DatabaseManager(database_url)
    db_manager.initialize()
    db_manager.create_tables()


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    return db_manager


class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass


class ConnectionError(DatabaseError):
    """Exception for database connection errors."""
    pass


class SessionError(DatabaseError):
    """Exception for database session errors."""
    pass


def handle_db_exceptions(func):
    """Decorator to handle common database exceptions."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DisconnectionError as e:
            logger.error(f"Database disconnection error in {func.__name__}: {e}")
            raise ConnectionError(f"Database connection lost: {e}")
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy error in {func.__name__}: {e}")
            raise DatabaseError(f"Database operation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise
    return wrapper


# Utility functions for common database operations
@handle_db_exceptions
def execute_query(query: str, params: Optional[dict] = None) -> list:
    """Execute a raw SQL query and return results."""
    with db_manager.get_session() as session:
        result = session.execute(query, params or {})
        return result.fetchall()


@handle_db_exceptions
def execute_update(query: str, params: Optional[dict] = None) -> int:
    """Execute an update/insert/delete query and return affected rows."""
    with db_manager.get_session() as session:
        result = session.execute(query, params or {})
        return result.rowcount