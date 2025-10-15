"""Common data models for the smart bug triage system."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum


class BugCategory(Enum):
    """Bug categories for classification."""
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    API = "api"
    MOBILE = "mobile"
    SECURITY = "security"
    PERFORMANCE = "performance"
    UNKNOWN = "unknown"


class Priority(Enum):
    """Bug priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AvailabilityStatus(Enum):
    """Developer availability status."""
    AVAILABLE = "available"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    FOCUS_TIME = "focus_time"


@dataclass
class BugReport:
    """Raw bug report from external systems."""
    id: str
    title: str
    description: str
    reporter: str
    created_at: datetime
    platform: str  # github, jira
    raw_data: Dict[str, Any]
    url: Optional[str] = None
    labels: Optional[List[str]] = None


@dataclass
class CategorizedBug:
    """Bug report with AI classification results."""
    bug_report: BugReport
    category: BugCategory
    severity: Priority
    keywords: List[str]
    confidence_score: float
    analysis_timestamp: datetime


@dataclass
class DeveloperProfile:
    """Static developer profile information."""
    id: str
    name: str
    github_username: str
    email: str
    skills: List[str]
    experience_level: str
    max_capacity: int
    preferred_categories: List[BugCategory]
    timezone: str


@dataclass
class DeveloperStatus:
    """Real-time developer status information."""
    developer_id: str
    current_workload: int
    open_issues_count: int
    complexity_score: float
    availability: AvailabilityStatus
    calendar_free: bool
    focus_time_active: bool
    last_activity_timestamp: datetime
    last_updated: datetime


@dataclass
class WorkloadInfo:
    """Developer workload calculation details."""
    total_issues: int
    complexity_breakdown: Dict[str, int]
    estimated_hours: float
    capacity_utilization: float


@dataclass
class Assignment:
    """Bug assignment record."""
    id: str
    bug_id: str
    developer_id: str
    assigned_at: datetime
    assignment_reason: str
    confidence_score: float
    status: str = "active"


@dataclass
class AssignmentFeedback:
    """Feedback on bug assignments."""
    assignment_id: str
    developer_id: str
    rating: int  # 1-5 scale
    comments: str
    resolution_time: Optional[int]  # minutes
    feedback_timestamp: datetime
    was_appropriate: bool


@dataclass
class AnalysisResult:
    """NLP analysis result for bug reports."""
    category_predictions: Dict[BugCategory, float]
    severity_prediction: Priority
    extracted_keywords: List[str]
    technical_terms: List[str]
    confidence_score: float
    processing_time: float