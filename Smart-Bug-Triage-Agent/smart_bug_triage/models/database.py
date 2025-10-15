"""SQLAlchemy database models for the smart bug triage system."""

from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, Boolean, 
    JSON, ForeignKey, Enum as SQLEnum, UniqueConstraint, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func

from .common import BugCategory, Priority, AvailabilityStatus

Base = declarative_base()


class Bug(Base):
    """SQLAlchemy model for bug reports."""
    __tablename__ = 'bugs'
    
    id = Column(String, primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    reporter = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False)
    platform = Column(String(50), nullable=False)  # github, jira
    url = Column(String(500))
    labels = Column(JSON)  # List of labels as JSON
    raw_data = Column(JSON)  # Original data from external system
    
    # Classification results (populated by Triage Agent)
    category = Column(SQLEnum(BugCategory), nullable=True)
    severity = Column(SQLEnum(Priority), nullable=True)
    keywords = Column(JSON)  # List of extracted keywords
    confidence_score = Column(Float, nullable=True)
    analysis_timestamp = Column(DateTime, nullable=True)
    
    # Relationships
    assignments = relationship("Assignment", back_populates="bug")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_bugs_created_at', 'created_at'),
        Index('idx_bugs_platform', 'platform'),
        Index('idx_bugs_category', 'category'),
        Index('idx_bugs_severity', 'severity'),
    )
    
    @validates('platform')
    def validate_platform(self, key, platform):
        allowed_platforms = ['github', 'jira']
        if platform not in allowed_platforms:
            raise ValueError(f"Platform must be one of {allowed_platforms}")
        return platform
    
    @validates('confidence_score')
    def validate_confidence_score(self, key, score):
        if score is not None and (score < 0.0 or score > 1.0):
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        return score


class Developer(Base):
    """SQLAlchemy model for developer profiles."""
    __tablename__ = 'developers'
    
    id = Column(String, primary_key=True)
    name = Column(String(100), nullable=False)
    github_username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    skills = Column(JSON, nullable=False)  # List of skills
    experience_level = Column(String(50), nullable=False)
    max_capacity = Column(Integer, nullable=False, default=10)
    preferred_categories = Column(JSON)  # List of BugCategory values
    timezone = Column(String(50), default='UTC')
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    status = relationship("DeveloperStatus", back_populates="developer", uselist=False)
    assignments = relationship("Assignment", back_populates="developer")
    feedback_given = relationship("AssignmentFeedback", back_populates="developer")
    workload_snapshots = relationship("WorkloadSnapshot", back_populates="developer")
    
    # Indexes
    __table_args__ = (
        Index('idx_developers_github_username', 'github_username'),
        Index('idx_developers_email', 'email'),
    )
    
    @validates('experience_level')
    def validate_experience_level(self, key, level):
        allowed_levels = ['junior', 'mid', 'senior', 'lead', 'principal']
        if level not in allowed_levels:
            raise ValueError(f"Experience level must be one of {allowed_levels}")
        return level
    
    @validates('max_capacity')
    def validate_max_capacity(self, key, capacity):
        if capacity < 1 or capacity > 50:
            raise ValueError("Max capacity must be between 1 and 50")
        return capacity


class DeveloperStatus(Base):
    """SQLAlchemy model for real-time developer status."""
    __tablename__ = 'developer_status'
    
    developer_id = Column(String, ForeignKey('developers.id'), primary_key=True)
    current_workload = Column(Integer, nullable=False, default=0)
    open_issues_count = Column(Integer, nullable=False, default=0)
    complexity_score = Column(Float, nullable=False, default=0.0)
    availability = Column(SQLEnum(AvailabilityStatus), nullable=False, default=AvailabilityStatus.AVAILABLE)
    calendar_free = Column(Boolean, nullable=False, default=True)
    focus_time_active = Column(Boolean, nullable=False, default=False)
    last_activity_timestamp = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    developer = relationship("Developer", back_populates="status")
    
    # Indexes
    __table_args__ = (
        Index('idx_developer_status_availability', 'availability'),
        Index('idx_developer_status_workload', 'current_workload'),
        Index('idx_developer_status_updated', 'last_updated'),
    )
    
    @validates('current_workload')
    def validate_workload(self, key, workload):
        if workload < 0:
            raise ValueError("Current workload cannot be negative")
        return workload
    
    @validates('complexity_score')
    def validate_complexity_score(self, key, score):
        if score < 0.0:
            raise ValueError("Complexity score cannot be negative")
        return score


class Assignment(Base):
    """SQLAlchemy model for bug assignments."""
    __tablename__ = 'assignments'
    
    id = Column(String, primary_key=True)
    bug_id = Column(String, ForeignKey('bugs.id'), nullable=False)
    developer_id = Column(String, ForeignKey('developers.id'), nullable=False)
    assigned_at = Column(DateTime, nullable=False, default=func.now())
    assignment_reason = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False)
    status = Column(String(50), nullable=False, default='active')
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    bug = relationship("Bug", back_populates="assignments")
    developer = relationship("Developer", back_populates="assignments")
    feedback = relationship("AssignmentFeedback", back_populates="assignment", uselist=False)
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('bug_id', 'developer_id', name='uq_bug_developer_assignment'),
        Index('idx_assignments_developer_id', 'developer_id'),
        Index('idx_assignments_bug_id', 'bug_id'),
        Index('idx_assignments_status', 'status'),
        Index('idx_assignments_assigned_at', 'assigned_at'),
    )
    
    @validates('status')
    def validate_status(self, key, status):
        allowed_statuses = ['active', 'completed', 'reassigned', 'cancelled']
        if status not in allowed_statuses:
            raise ValueError(f"Status must be one of {allowed_statuses}")
        return status
    
    @validates('confidence_score')
    def validate_confidence_score(self, key, score):
        if score < 0.0 or score > 1.0:
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        return score


class AssignmentFeedback(Base):
    """SQLAlchemy model for assignment feedback."""
    __tablename__ = 'assignment_feedback'
    
    id = Column(String, primary_key=True)
    assignment_id = Column(String, ForeignKey('assignments.id'), nullable=False, unique=True)
    developer_id = Column(String, ForeignKey('developers.id'), nullable=False)
    rating = Column(Integer, nullable=False)
    comments = Column(Text)
    resolution_time = Column(Integer, nullable=True)  # minutes
    was_appropriate = Column(Boolean, nullable=False)
    feedback_timestamp = Column(DateTime, nullable=False, default=func.now())
    
    # Relationships
    assignment = relationship("Assignment", back_populates="feedback")
    developer = relationship("Developer", back_populates="feedback_given")
    
    # Indexes
    __table_args__ = (
        Index('idx_feedback_developer_id', 'developer_id'),
        Index('idx_feedback_rating', 'rating'),
        Index('idx_feedback_timestamp', 'feedback_timestamp'),
        Index('idx_feedback_appropriate', 'was_appropriate'),
    )
    
    @validates('rating')
    def validate_rating(self, key, rating):
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")
        return rating
    
    @validates('resolution_time')
    def validate_resolution_time(self, key, time):
        if time is not None and time < 0:
            raise ValueError("Resolution time cannot be negative")
        return time


class WorkloadSnapshot(Base):
    """SQLAlchemy model for historical workload tracking."""
    __tablename__ = 'workload_snapshots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    developer_id = Column(String, ForeignKey('developers.id'), nullable=False)
    workload_score = Column(Integer, nullable=False)
    issue_count = Column(Integer, nullable=False)
    complexity_breakdown = Column(JSON, nullable=False)  # Dict of complexity metrics
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    
    # Relationships
    developer = relationship("Developer", back_populates="workload_snapshots")
    
    # Indexes
    __table_args__ = (
        Index('idx_workload_developer_time', 'developer_id', 'snapshot_time'),
        Index('idx_workload_snapshot_time', 'snapshot_time'),
    )


class AgentState(Base):
    """SQLAlchemy model for agent status and configuration."""
    __tablename__ = 'agent_states'
    
    agent_id = Column(String, primary_key=True)
    agent_type = Column(String(50), nullable=False)  # listener, triage, assignment, developer
    status = Column(String(50), nullable=False, default='inactive')
    configuration = Column(JSON)  # Agent-specific configuration
    last_heartbeat = Column(DateTime, nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_agent_states_type', 'agent_type'),
        Index('idx_agent_states_status', 'status'),
        Index('idx_agent_states_heartbeat', 'last_heartbeat'),
    )
    
    @validates('agent_type')
    def validate_agent_type(self, key, agent_type):
        allowed_types = ['listener', 'triage', 'assignment', 'developer']
        if agent_type not in allowed_types:
            raise ValueError(f"Agent type must be one of {allowed_types}")
        return agent_type
    
    @validates('status')
    def validate_status(self, key, status):
        allowed_statuses = ['active', 'inactive', 'error', 'maintenance']
        if status not in allowed_statuses:
            raise ValueError(f"Status must be one of {allowed_statuses}")
        return status


class SystemMetric(Base):
    """SQLAlchemy model for system performance metrics."""
    __tablename__ = 'system_metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    metric_type = Column(String(50), nullable=False)  # counter, gauge, histogram, timer
    tags = Column(JSON)  # Additional metadata as key-value pairs
    timestamp = Column(DateTime, nullable=False, default=func.now())
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_metrics_name_timestamp', 'metric_name', 'timestamp'),
        Index('idx_metrics_type', 'metric_type'),
        Index('idx_metrics_timestamp', 'timestamp'),
    )
    
    @validates('metric_type')
    def validate_metric_type(self, key, metric_type):
        allowed_types = ['counter', 'gauge', 'histogram', 'timer']
        if metric_type not in allowed_types:
            raise ValueError(f"Metric type must be one of {allowed_types}")
        return metric_type


class AssignmentAccuracy(Base):
    """SQLAlchemy model for tracking assignment accuracy metrics."""
    __tablename__ = 'assignment_accuracy'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_id = Column(String, ForeignKey('assignments.id'), nullable=False)
    predicted_category = Column(SQLEnum(BugCategory), nullable=False)
    actual_category = Column(SQLEnum(BugCategory), nullable=True)
    predicted_developer = Column(String, ForeignKey('developers.id'), nullable=False)
    feedback_rating = Column(Integer, nullable=True)  # 1-5 from developer feedback
    resolution_time_minutes = Column(Integer, nullable=True)
    was_reassigned = Column(Boolean, nullable=False, default=False)
    accuracy_score = Column(Float, nullable=True)  # Calculated accuracy score
    recorded_at = Column(DateTime, nullable=False, default=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_accuracy_assignment', 'assignment_id'),
        Index('idx_accuracy_category', 'predicted_category', 'actual_category'),
        Index('idx_accuracy_developer', 'predicted_developer'),
        Index('idx_accuracy_recorded', 'recorded_at'),
    )


class ProcessingMetrics(Base):
    """SQLAlchemy model for tracking processing time and throughput."""
    __tablename__ = 'processing_metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    process_type = Column(String(50), nullable=False)  # bug_detection, triage, assignment
    process_id = Column(String, nullable=False)  # bug_id or assignment_id
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    throughput_items = Column(Integer, nullable=False, default=1)
    
    # Indexes
    __table_args__ = (
        Index('idx_processing_type_time', 'process_type', 'start_time'),
        Index('idx_processing_success', 'success'),
        Index('idx_processing_duration', 'duration_ms'),
    )
    
    @validates('process_type')
    def validate_process_type(self, key, process_type):
        allowed_types = ['bug_detection', 'triage', 'assignment', 'notification', 'feedback_processing']
        if process_type not in allowed_types:
            raise ValueError(f"Process type must be one of {allowed_types}")
        return process_type


class SystemAlert(Base):
    """SQLAlchemy model for system alerts and notifications."""
    __tablename__ = 'system_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_name = Column(String(100), nullable=False)
    alert_type = Column(String(50), nullable=False)  # performance, error, health
    severity = Column(String(20), nullable=False)  # low, medium, high, critical
    message = Column(Text, nullable=False)
    metric_name = Column(String(100), nullable=True)
    metric_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    triggered_at = Column(DateTime, nullable=False, default=func.now())
    resolved_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_alerts_active', 'is_active'),
        Index('idx_alerts_severity', 'severity'),
        Index('idx_alerts_type', 'alert_type'),
        Index('idx_alerts_triggered', 'triggered_at'),
    )
    
    @validates('alert_type')
    def validate_alert_type(self, key, alert_type):
        allowed_types = ['performance', 'error', 'health', 'capacity', 'accuracy']
        if alert_type not in allowed_types:
            raise ValueError(f"Alert type must be one of {allowed_types}")
        return alert_type
    
    @validates('severity')
    def validate_severity(self, key, severity):
        allowed_severities = ['low', 'medium', 'high', 'critical']
        if severity not in allowed_severities:
            raise ValueError(f"Severity must be one of {allowed_severities}")
        return severity