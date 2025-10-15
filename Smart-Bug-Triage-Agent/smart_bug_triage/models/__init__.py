"""Data models and database schemas."""

# Common data classes and enums
from .common import (
    BugCategory,
    Priority,
    AvailabilityStatus,
    BugReport,
    CategorizedBug,
    DeveloperProfile,
    DeveloperStatus,
    WorkloadInfo,
    Assignment,
    AssignmentFeedback,
    AnalysisResult
)

# SQLAlchemy database models
from .database import (
    Base,
    Bug,
    Developer,
    DeveloperStatus as DeveloperStatusModel,
    Assignment as AssignmentModel,
    AssignmentFeedback as AssignmentFeedbackModel,
    WorkloadSnapshot,
    AgentState
)

# Validation classes
from .validation import (
    ValidationError,
    BugReportValidator,
    DeveloperProfileValidator,
    DeveloperStatusValidator,
    AssignmentValidator,
    AssignmentFeedbackValidator,
    validate_bug_report,
    validate_developer_profile,
    validate_developer_status,
    validate_assignment,
    validate_assignment_feedback,
    validate_multiple_bug_reports,
    validate_multiple_developer_profiles
)

__all__ = [
    # Enums
    'BugCategory',
    'Priority',
    'AvailabilityStatus',
    
    # Common data classes
    'BugReport',
    'CategorizedBug',
    'DeveloperProfile',
    'DeveloperStatus',
    'WorkloadInfo',
    'Assignment',
    'AssignmentFeedback',
    'AnalysisResult',
    
    # SQLAlchemy models
    'Base',
    'Bug',
    'Developer',
    'DeveloperStatusModel',
    'AssignmentModel',
    'AssignmentFeedbackModel',
    'WorkloadSnapshot',
    'AgentState',
    
    # Validation
    'ValidationError',
    'BugReportValidator',
    'DeveloperProfileValidator',
    'DeveloperStatusValidator',
    'AssignmentValidator',
    'AssignmentFeedbackValidator',
    'validate_bug_report',
    'validate_developer_profile',
    'validate_developer_status',
    'validate_assignment',
    'validate_assignment_feedback',
    'validate_multiple_bug_reports',
    'validate_multiple_developer_profiles'
]