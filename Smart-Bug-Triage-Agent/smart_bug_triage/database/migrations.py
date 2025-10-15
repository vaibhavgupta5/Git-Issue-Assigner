"""Database migration utilities and scripts."""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

from .connection import DatabaseManager, handle_db_exceptions
from ..models.database import Base

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.migration_table = 'schema_migrations'
    
    def _ensure_migration_table(self) -> None:
        """Create migration tracking table if it doesn't exist."""
        create_migration_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.migration_table} (
            version VARCHAR(50) PRIMARY KEY,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checksum VARCHAR(64)
        );
        """
        
        with self.db_manager.get_session() as session:
            session.execute(text(create_migration_table_sql))
    
    @handle_db_exceptions
    def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        self._ensure_migration_table()
        
        with self.db_manager.get_session() as session:
            result = session.execute(
                text(f"SELECT version FROM {self.migration_table} ORDER BY applied_at")
            )
            return [row[0] for row in result.fetchall()]
    
    @handle_db_exceptions
    def record_migration(self, version: str, description: str, checksum: str) -> None:
        """Record a migration as applied."""
        with self.db_manager.get_session() as session:
            session.execute(
                text(f"""
                INSERT INTO {self.migration_table} (version, description, checksum)
                VALUES (:version, :description, :checksum)
                """),
                {
                    'version': version,
                    'description': description,
                    'checksum': checksum
                }
            )
    
    @handle_db_exceptions
    def apply_migration(self, migration: 'Migration') -> None:
        """Apply a single migration."""
        logger.info(f"Applying migration {migration.version}: {migration.description}")
        
        try:
            # Ensure migration table exists first
            self._ensure_migration_table()
            
            with self.db_manager.get_session() as session:
                # Execute migration SQL
                for sql_statement in migration.up_sql:
                    session.execute(text(sql_statement))
                
            # Record migration in separate transaction
            self.record_migration(
                migration.version,
                migration.description,
                migration.checksum
            )
            
            logger.info(f"Migration {migration.version} applied successfully")
            
        except Exception as e:
            logger.error(f"Failed to apply migration {migration.version}: {e}")
            raise
    
    @handle_db_exceptions
    def rollback_migration(self, migration: 'Migration') -> None:
        """Rollback a single migration."""
        logger.info(f"Rolling back migration {migration.version}: {migration.description}")
        
        try:
            with self.db_manager.get_session() as session:
                # Execute rollback SQL
                for sql_statement in migration.down_sql:
                    session.execute(text(sql_statement))
                
                # Remove migration record
                session.execute(
                    text(f"DELETE FROM {self.migration_table} WHERE version = :version"),
                    {'version': migration.version}
                )
            
            logger.info(f"Migration {migration.version} rolled back successfully")
            
        except Exception as e:
            logger.error(f"Failed to rollback migration {migration.version}: {e}")
            raise
    
    def get_pending_migrations(self) -> List['Migration']:
        """Get list of migrations that need to be applied."""
        applied = set(self.get_applied_migrations())
        all_migrations = get_all_migrations()
        
        return [m for m in all_migrations if m.version not in applied]
    
    def migrate_up(self) -> None:
        """Apply all pending migrations."""
        pending = self.get_pending_migrations()
        
        if not pending:
            logger.info("No pending migrations")
            return
        
        logger.info(f"Applying {len(pending)} pending migrations")
        
        for migration in pending:
            self.apply_migration(migration)
        
        logger.info("All migrations applied successfully")
    
    def migrate_down(self, target_version: Optional[str] = None) -> None:
        """Rollback migrations to target version."""
        applied = self.get_applied_migrations()
        all_migrations = {m.version: m for m in get_all_migrations()}
        
        if target_version:
            # Rollback to specific version
            rollback_versions = []
            for version in reversed(applied):
                if version == target_version:
                    break
                rollback_versions.append(version)
        else:
            # Rollback all migrations
            rollback_versions = list(reversed(applied))
        
        logger.info(f"Rolling back {len(rollback_versions)} migrations")
        
        for version in rollback_versions:
            if version in all_migrations:
                self.rollback_migration(all_migrations[version])
        
        logger.info("Rollback completed successfully")


class Migration:
    """Represents a database migration."""
    
    def __init__(
        self,
        version: str,
        description: str,
        up_sql: List[str],
        down_sql: List[str]
    ):
        self.version = version
        self.description = description
        self.up_sql = up_sql
        self.down_sql = down_sql
        self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> str:
        """Calculate checksum for migration integrity."""
        import hashlib
        content = f"{self.version}{self.description}{''.join(self.up_sql)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_all_migrations() -> List[Migration]:
    """Get all available migrations in order."""
    return [
        Migration(
            version="001_initial_schema",
            description="Create initial database schema",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS bugs (
                    id VARCHAR PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    description TEXT NOT NULL,
                    reporter VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    platform VARCHAR(50) NOT NULL,
                    url VARCHAR(500),
                    labels JSONB,
                    raw_data JSONB,
                    category VARCHAR(50),
                    severity VARCHAR(50),
                    keywords JSONB,
                    confidence_score FLOAT,
                    analysis_timestamp TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS developers (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    github_username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(200) UNIQUE NOT NULL,
                    skills JSONB NOT NULL,
                    experience_level VARCHAR(50) NOT NULL,
                    max_capacity INTEGER NOT NULL DEFAULT 10,
                    preferred_categories JSONB,
                    timezone VARCHAR(50) DEFAULT 'UTC',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS developer_status (
                    developer_id VARCHAR PRIMARY KEY REFERENCES developers(id),
                    current_workload INTEGER NOT NULL DEFAULT 0,
                    open_issues_count INTEGER NOT NULL DEFAULT 0,
                    complexity_score FLOAT NOT NULL DEFAULT 0.0,
                    availability VARCHAR(50) NOT NULL DEFAULT 'available',
                    calendar_free BOOLEAN NOT NULL DEFAULT TRUE,
                    focus_time_active BOOLEAN NOT NULL DEFAULT FALSE,
                    last_activity_timestamp TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    id VARCHAR PRIMARY KEY,
                    bug_id VARCHAR NOT NULL REFERENCES bugs(id),
                    developer_id VARCHAR NOT NULL REFERENCES developers(id),
                    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    assignment_reason TEXT NOT NULL,
                    confidence_score FLOAT NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'active',
                    completed_at TIMESTAMP,
                    UNIQUE(bug_id, developer_id)
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS assignment_feedback (
                    id VARCHAR PRIMARY KEY,
                    assignment_id VARCHAR NOT NULL UNIQUE REFERENCES assignments(id),
                    developer_id VARCHAR NOT NULL REFERENCES developers(id),
                    rating INTEGER NOT NULL,
                    comments TEXT,
                    resolution_time INTEGER,
                    was_appropriate BOOLEAN NOT NULL,
                    feedback_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS workload_snapshots (
                    id SERIAL PRIMARY KEY,
                    developer_id VARCHAR NOT NULL REFERENCES developers(id),
                    workload_score INTEGER NOT NULL,
                    issue_count INTEGER NOT NULL,
                    complexity_breakdown JSONB NOT NULL,
                    snapshot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS agent_states (
                    agent_id VARCHAR PRIMARY KEY,
                    agent_type VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'inactive',
                    configuration JSONB,
                    last_heartbeat TIMESTAMP,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            ],
            down_sql=[
                "DROP TABLE IF EXISTS agent_states CASCADE;",
                "DROP TABLE IF EXISTS workload_snapshots CASCADE;",
                "DROP TABLE IF EXISTS assignment_feedback CASCADE;",
                "DROP TABLE IF EXISTS assignments CASCADE;",
                "DROP TABLE IF EXISTS developer_status CASCADE;",
                "DROP TABLE IF EXISTS developers CASCADE;",
                "DROP TABLE IF EXISTS bugs CASCADE;"
            ]
        ),
        Migration(
            version="002_add_indexes",
            description="Add performance indexes",
            up_sql=[
                "CREATE INDEX IF NOT EXISTS idx_bugs_created_at ON bugs(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_bugs_platform ON bugs(platform);",
                "CREATE INDEX IF NOT EXISTS idx_bugs_category ON bugs(category);",
                "CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bugs(severity);",
                "CREATE INDEX IF NOT EXISTS idx_developers_github_username ON developers(github_username);",
                "CREATE INDEX IF NOT EXISTS idx_developers_email ON developers(email);",
                "CREATE INDEX IF NOT EXISTS idx_developer_status_availability ON developer_status(availability);",
                "CREATE INDEX IF NOT EXISTS idx_developer_status_workload ON developer_status(current_workload);",
                "CREATE INDEX IF NOT EXISTS idx_developer_status_updated ON developer_status(last_updated);",
                "CREATE INDEX IF NOT EXISTS idx_assignments_developer_id ON assignments(developer_id);",
                "CREATE INDEX IF NOT EXISTS idx_assignments_bug_id ON assignments(bug_id);",
                "CREATE INDEX IF NOT EXISTS idx_assignments_status ON assignments(status);",
                "CREATE INDEX IF NOT EXISTS idx_assignments_assigned_at ON assignments(assigned_at);",
                "CREATE INDEX IF NOT EXISTS idx_feedback_developer_id ON assignment_feedback(developer_id);",
                "CREATE INDEX IF NOT EXISTS idx_feedback_rating ON assignment_feedback(rating);",
                "CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON assignment_feedback(feedback_timestamp);",
                "CREATE INDEX IF NOT EXISTS idx_feedback_appropriate ON assignment_feedback(was_appropriate);",
                "CREATE INDEX IF NOT EXISTS idx_workload_developer_time ON workload_snapshots(developer_id, snapshot_time);",
                "CREATE INDEX IF NOT EXISTS idx_workload_snapshot_time ON workload_snapshots(snapshot_time);",
                "CREATE INDEX IF NOT EXISTS idx_agent_states_type ON agent_states(agent_type);",
                "CREATE INDEX IF NOT EXISTS idx_agent_states_status ON agent_states(status);",
                "CREATE INDEX IF NOT EXISTS idx_agent_states_heartbeat ON agent_states(last_heartbeat);"
            ],
            down_sql=[
                "DROP INDEX IF EXISTS idx_bugs_created_at;",
                "DROP INDEX IF EXISTS idx_bugs_platform;",
                "DROP INDEX IF EXISTS idx_bugs_category;",
                "DROP INDEX IF EXISTS idx_bugs_severity;",
                "DROP INDEX IF EXISTS idx_developers_github_username;",
                "DROP INDEX IF EXISTS idx_developers_email;",
                "DROP INDEX IF EXISTS idx_developer_status_availability;",
                "DROP INDEX IF EXISTS idx_developer_status_workload;",
                "DROP INDEX IF EXISTS idx_developer_status_updated;",
                "DROP INDEX IF EXISTS idx_assignments_developer_id;",
                "DROP INDEX IF EXISTS idx_assignments_bug_id;",
                "DROP INDEX IF EXISTS idx_assignments_status;",
                "DROP INDEX IF EXISTS idx_assignments_assigned_at;",
                "DROP INDEX IF EXISTS idx_feedback_developer_id;",
                "DROP INDEX IF EXISTS idx_feedback_rating;",
                "DROP INDEX IF EXISTS idx_feedback_timestamp;",
                "DROP INDEX IF EXISTS idx_feedback_appropriate;",
                "DROP INDEX IF EXISTS idx_workload_developer_time;",
                "DROP INDEX IF EXISTS idx_workload_snapshot_time;",
                "DROP INDEX IF EXISTS idx_agent_states_type;",
                "DROP INDEX IF EXISTS idx_agent_states_status;",
                "DROP INDEX IF EXISTS idx_agent_states_heartbeat;"
            ]
        ),
        Migration(
            version="003_notification_system",
            description="Add notification system tables",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS notification_preferences (
                    developer_id VARCHAR PRIMARY KEY REFERENCES developers(id),
                    email_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    slack_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    in_app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    channels_by_type JSONB NOT NULL DEFAULT '{}',
                    quiet_hours_start VARCHAR(5),
                    quiet_hours_end VARCHAR(5),
                    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS notification_requests (
                    id VARCHAR PRIMARY KEY,
                    notification_type VARCHAR(50) NOT NULL,
                    recipient_id VARCHAR NOT NULL,
                    channels JSONB NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 1,
                    context_data JSONB NOT NULL,
                    scheduled_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS notification_results (
                    id SERIAL PRIMARY KEY,
                    request_id VARCHAR NOT NULL REFERENCES notification_requests(id),
                    channel VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    message TEXT,
                    delivered_at TIMESTAMP,
                    error_details TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS notification_templates (
                    id SERIAL PRIMARY KEY,
                    notification_type VARCHAR(50) NOT NULL,
                    channel VARCHAR(50) NOT NULL,
                    subject_template TEXT NOT NULL,
                    body_template TEXT NOT NULL,
                    format_type VARCHAR(20) NOT NULL DEFAULT 'text',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(notification_type, channel)
                );
                """
            ],
            down_sql=[
                "DROP TABLE IF EXISTS notification_templates CASCADE;",
                "DROP TABLE IF EXISTS notification_results CASCADE;",
                "DROP TABLE IF EXISTS notification_requests CASCADE;",
                "DROP TABLE IF EXISTS notification_preferences CASCADE;"
            ]
        ),
        Migration(
            version="004_notification_indexes",
            description="Add notification system indexes",
            up_sql=[
                "CREATE INDEX IF NOT EXISTS idx_notification_preferences_developer ON notification_preferences(developer_id);",
                "CREATE INDEX IF NOT EXISTS idx_notification_requests_type ON notification_requests(notification_type);",
                "CREATE INDEX IF NOT EXISTS idx_notification_requests_recipient ON notification_requests(recipient_id);",
                "CREATE INDEX IF NOT EXISTS idx_notification_requests_created ON notification_requests(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_notification_requests_scheduled ON notification_requests(scheduled_at);",
                "CREATE INDEX IF NOT EXISTS idx_notification_results_request ON notification_results(request_id);",
                "CREATE INDEX IF NOT EXISTS idx_notification_results_channel ON notification_results(channel);",
                "CREATE INDEX IF NOT EXISTS idx_notification_results_status ON notification_results(status);",
                "CREATE INDEX IF NOT EXISTS idx_notification_results_delivered ON notification_results(delivered_at);",
                "CREATE INDEX IF NOT EXISTS idx_notification_results_retry ON notification_results(next_retry_at);",
                "CREATE INDEX IF NOT EXISTS idx_notification_templates_type_channel ON notification_templates(notification_type, channel);",
                "CREATE INDEX IF NOT EXISTS idx_notification_templates_active ON notification_templates(is_active);"
            ],
            down_sql=[
                "DROP INDEX IF EXISTS idx_notification_preferences_developer;",
                "DROP INDEX IF EXISTS idx_notification_requests_type;",
                "DROP INDEX IF EXISTS idx_notification_requests_recipient;",
                "DROP INDEX IF EXISTS idx_notification_requests_created;",
                "DROP INDEX IF EXISTS idx_notification_requests_scheduled;",
                "DROP INDEX IF EXISTS idx_notification_results_request;",
                "DROP INDEX IF EXISTS idx_notification_results_channel;",
                "DROP INDEX IF EXISTS idx_notification_results_status;",
                "DROP INDEX IF EXISTS idx_notification_results_delivered;",
                "DROP INDEX IF EXISTS idx_notification_results_retry;",
                "DROP INDEX IF EXISTS idx_notification_templates_type_channel;",
                "DROP INDEX IF EXISTS idx_notification_templates_active;"
            ]
        ),
        Migration(
            version="005_monitoring_system",
            description="Add monitoring and metrics system tables",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id SERIAL PRIMARY KEY,
                    metric_name VARCHAR(100) NOT NULL,
                    metric_value FLOAT NOT NULL,
                    metric_type VARCHAR(50) NOT NULL,
                    tags JSONB,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS assignment_accuracy (
                    id SERIAL PRIMARY KEY,
                    assignment_id VARCHAR NOT NULL REFERENCES assignments(id),
                    predicted_category VARCHAR(50) NOT NULL,
                    actual_category VARCHAR(50),
                    predicted_developer VARCHAR NOT NULL REFERENCES developers(id),
                    feedback_rating INTEGER,
                    resolution_time_minutes INTEGER,
                    was_reassigned BOOLEAN NOT NULL DEFAULT FALSE,
                    accuracy_score FLOAT,
                    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS processing_metrics (
                    id SERIAL PRIMARY KEY,
                    process_type VARCHAR(50) NOT NULL,
                    process_id VARCHAR NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    throughput_items INTEGER NOT NULL DEFAULT 1
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS system_alerts (
                    id SERIAL PRIMARY KEY,
                    alert_name VARCHAR(100) NOT NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    metric_name VARCHAR(100),
                    metric_value FLOAT,
                    threshold_value FLOAT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    triggered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    acknowledged_at TIMESTAMP
                );
                """
            ],
            down_sql=[
                "DROP TABLE IF EXISTS system_alerts CASCADE;",
                "DROP TABLE IF EXISTS processing_metrics CASCADE;",
                "DROP TABLE IF EXISTS assignment_accuracy CASCADE;",
                "DROP TABLE IF EXISTS system_metrics CASCADE;"
            ]
        ),
        Migration(
            version="006_monitoring_indexes",
            description="Add monitoring system indexes",
            up_sql=[
                "CREATE INDEX IF NOT EXISTS idx_metrics_name_timestamp ON system_metrics(metric_name, timestamp);",
                "CREATE INDEX IF NOT EXISTS idx_metrics_type ON system_metrics(metric_type);",
                "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON system_metrics(timestamp);",
                "CREATE INDEX IF NOT EXISTS idx_accuracy_assignment ON assignment_accuracy(assignment_id);",
                "CREATE INDEX IF NOT EXISTS idx_accuracy_category ON assignment_accuracy(predicted_category, actual_category);",
                "CREATE INDEX IF NOT EXISTS idx_accuracy_developer ON assignment_accuracy(predicted_developer);",
                "CREATE INDEX IF NOT EXISTS idx_accuracy_recorded ON assignment_accuracy(recorded_at);",
                "CREATE INDEX IF NOT EXISTS idx_processing_type_time ON processing_metrics(process_type, start_time);",
                "CREATE INDEX IF NOT EXISTS idx_processing_success ON processing_metrics(success);",
                "CREATE INDEX IF NOT EXISTS idx_processing_duration ON processing_metrics(duration_ms);",
                "CREATE INDEX IF NOT EXISTS idx_alerts_active ON system_alerts(is_active);",
                "CREATE INDEX IF NOT EXISTS idx_alerts_severity ON system_alerts(severity);",
                "CREATE INDEX IF NOT EXISTS idx_alerts_type ON system_alerts(alert_type);",
                "CREATE INDEX IF NOT EXISTS idx_alerts_triggered ON system_alerts(triggered_at);"
            ],
            down_sql=[
                "DROP INDEX IF EXISTS idx_metrics_name_timestamp;",
                "DROP INDEX IF EXISTS idx_metrics_type;",
                "DROP INDEX IF EXISTS idx_metrics_timestamp;",
                "DROP INDEX IF EXISTS idx_accuracy_assignment;",
                "DROP INDEX IF EXISTS idx_accuracy_category;",
                "DROP INDEX IF EXISTS idx_accuracy_developer;",
                "DROP INDEX IF EXISTS idx_accuracy_recorded;",
                "DROP INDEX IF EXISTS idx_processing_type_time;",
                "DROP INDEX IF EXISTS idx_processing_success;",
                "DROP INDEX IF EXISTS idx_processing_duration;",
                "DROP INDEX IF EXISTS idx_alerts_active;",
                "DROP INDEX IF EXISTS idx_alerts_severity;",
                "DROP INDEX IF EXISTS idx_alerts_type;",
                "DROP INDEX IF EXISTS idx_alerts_triggered;"
            ]
        )
    ]


def run_migrations(db_manager: DatabaseManager) -> None:
    """Run all pending migrations."""
    migration_manager = MigrationManager(db_manager)
    migration_manager.migrate_up()


def rollback_migrations(db_manager: DatabaseManager, target_version: Optional[str] = None) -> None:
    """Rollback migrations to target version."""
    migration_manager = MigrationManager(db_manager)
    migration_manager.migrate_down(target_version)


def check_migration_status(db_manager: DatabaseManager) -> Dict[str, Any]:
    """Check current migration status."""
    migration_manager = MigrationManager(db_manager)
    applied = migration_manager.get_applied_migrations()
    pending = migration_manager.get_pending_migrations()
    
    return {
        'applied_migrations': applied,
        'pending_migrations': [m.version for m in pending],
        'total_migrations': len(get_all_migrations()),
        'up_to_date': len(pending) == 0
    }