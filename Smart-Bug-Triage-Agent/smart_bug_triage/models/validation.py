"""Data validation classes for bug reports and developer profiles."""

import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from pydantic import BaseModel, validator, Field
from enum import Enum

from .common import BugCategory, Priority, AvailabilityStatus


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class BugReportValidator(BaseModel):
    """Pydantic validator for bug reports."""
    
    id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=10, max_length=10000)
    reporter: str = Field(..., min_length=1, max_length=100)
    created_at: datetime
    platform: str = Field(..., pattern=r'^(github|jira)$')
    url: Optional[str] = Field(None, max_length=500)
    labels: Optional[List[str]] = Field(None, max_items=20)
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    
    # Classification fields (optional, populated by Triage Agent)
    category: Optional[BugCategory] = None
    severity: Optional[Priority] = None
    keywords: Optional[List[str]] = Field(None, max_items=50)
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    analysis_timestamp: Optional[datetime] = None
    
    @validator('id')
    def validate_id(cls, v):
        """Validate bug ID format."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Bug ID must contain only alphanumeric characters, underscores, and hyphens')
        return v
    
    @validator('title')
    def validate_title(cls, v):
        """Validate bug title."""
        if not v.strip():
            raise ValueError('Bug title cannot be empty or whitespace only')
        return v.strip()
    
    @validator('description')
    def validate_description(cls, v):
        """Validate bug description."""
        if not v.strip():
            raise ValueError('Bug description cannot be empty or whitespace only')
        if len(v.strip()) < 10:
            raise ValueError('Bug description must be at least 10 characters long')
        return v.strip()
    
    @validator('url')
    def validate_url(cls, v):
        """Validate bug URL format."""
        if v is None:
            return v
        
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(v):
            raise ValueError('Invalid URL format')
        return v
    
    @validator('labels')
    def validate_labels(cls, v):
        """Validate bug labels."""
        if v is None:
            return v
        
        # Remove duplicates and empty labels
        cleaned_labels = list(set(label.strip() for label in v if label.strip()))
        
        # Validate each label
        for label in cleaned_labels:
            if len(label) > 50:
                raise ValueError(f'Label "{label}" is too long (max 50 characters)')
            if not re.match(r'^[a-zA-Z0-9_\-\s]+$', label):
                raise ValueError(f'Label "{label}" contains invalid characters')
        
        return cleaned_labels
    
    @validator('keywords')
    def validate_keywords(cls, v):
        """Validate extracted keywords."""
        if v is None:
            return v
        
        # Remove duplicates and empty keywords
        cleaned_keywords = list(set(keyword.strip().lower() for keyword in v if keyword.strip()))
        
        # Validate each keyword
        for keyword in cleaned_keywords:
            if len(keyword) > 100:
                raise ValueError(f'Keyword "{keyword}" is too long (max 100 characters)')
        
        return cleaned_keywords
    
    @validator('raw_data')
    def validate_raw_data(cls, v):
        """Validate raw data structure."""
        if not isinstance(v, dict):
            raise ValueError('Raw data must be a dictionary')
        
        # Check for required fields based on platform
        return v
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        validate_assignment = True


class DeveloperProfileValidator(BaseModel):
    """Pydantic validator for developer profiles."""
    
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    github_username: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    skills: List[str] = Field(..., min_items=1, max_items=50)
    experience_level: str = Field(..., pattern=r'^(junior|mid|senior|lead|principal)$')
    max_capacity: int = Field(..., ge=1, le=50)
    preferred_categories: Optional[List[BugCategory]] = Field(None, max_items=10)
    timezone: str = Field(default='UTC', max_length=50)
    
    @validator('id')
    def validate_id(cls, v):
        """Validate developer ID format."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Developer ID must contain only alphanumeric characters, underscores, and hyphens')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        """Validate developer name."""
        if not v.strip():
            raise ValueError('Developer name cannot be empty or whitespace only')
        if not re.match(r'^[a-zA-Z\s\-\.\']+$', v.strip()):
            raise ValueError('Developer name contains invalid characters')
        return v.strip()
    
    @validator('github_username')
    def validate_github_username(cls, v):
        """Validate GitHub username format."""
        if not re.match(r'^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$', v):
            raise ValueError('Invalid GitHub username format')
        return v
    
    @validator('skills')
    def validate_skills(cls, v):
        """Validate developer skills."""
        if not v:
            raise ValueError('Developer must have at least one skill')
        
        # Remove duplicates and empty skills
        cleaned_skills = list(set(skill.strip() for skill in v if skill.strip()))
        
        if not cleaned_skills:
            raise ValueError('Developer must have at least one valid skill')
        
        # Validate each skill
        for skill in cleaned_skills:
            if len(skill) > 50:
                raise ValueError(f'Skill "{skill}" is too long (max 50 characters)')
            if not re.match(r'^[a-zA-Z0-9_\-\s\+\#\.]+$', skill):
                raise ValueError(f'Skill "{skill}" contains invalid characters')
        
        return cleaned_skills
    
    @validator('preferred_categories')
    def validate_preferred_categories(cls, v):
        """Validate preferred bug categories."""
        if v is None:
            return v
        
        # Remove duplicates
        return list(set(v))
    
    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone format."""
        # Basic timezone validation - could be enhanced with pytz
        if not re.match(r'^[A-Za-z/_\-\+0-9]+$', v):
            raise ValueError('Invalid timezone format')
        return v
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        validate_assignment = True


class DeveloperStatusValidator(BaseModel):
    """Pydantic validator for developer status."""
    
    developer_id: str = Field(..., min_length=1, max_length=100)
    current_workload: int = Field(..., ge=0)
    open_issues_count: int = Field(..., ge=0)
    complexity_score: float = Field(..., ge=0.0)
    availability: AvailabilityStatus
    calendar_free: bool
    focus_time_active: bool
    last_activity_timestamp: Optional[datetime] = None
    last_updated: datetime
    
    @validator('current_workload')
    def validate_workload(cls, v, values):
        """Validate workload is reasonable."""
        if 'open_issues_count' in values and v < values['open_issues_count']:
            raise ValueError('Current workload cannot be less than open issues count')
        return v
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        validate_assignment = True


class AssignmentValidator(BaseModel):
    """Pydantic validator for bug assignments."""
    
    id: str = Field(..., min_length=1, max_length=100)
    bug_id: str = Field(..., min_length=1, max_length=100)
    developer_id: str = Field(..., min_length=1, max_length=100)
    assigned_at: datetime
    assignment_reason: str = Field(..., min_length=10, max_length=1000)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(default='active', pattern=r'^(active|completed|reassigned|cancelled)$')
    completed_at: Optional[datetime] = None
    
    @validator('assignment_reason')
    def validate_assignment_reason(cls, v):
        """Validate assignment reasoning."""
        if not v.strip():
            raise ValueError('Assignment reason cannot be empty')
        return v.strip()
    
    @validator('completed_at')
    def validate_completed_at(cls, v, values):
        """Validate completion timestamp."""
        if v is not None and 'assigned_at' in values:
            if v < values['assigned_at']:
                raise ValueError('Completion time cannot be before assignment time')
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class AssignmentFeedbackValidator(BaseModel):
    """Pydantic validator for assignment feedback."""
    
    id: str = Field(..., min_length=1, max_length=100)
    assignment_id: str = Field(..., min_length=1, max_length=100)
    developer_id: str = Field(..., min_length=1, max_length=100)
    rating: int = Field(..., ge=1, le=5)
    comments: Optional[str] = Field(None, max_length=2000)
    resolution_time: Optional[int] = Field(None, ge=0)  # minutes
    was_appropriate: bool
    feedback_timestamp: datetime
    
    @validator('comments')
    def validate_comments(cls, v):
        """Validate feedback comments."""
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


# Utility functions for validation
def validate_bug_report(data: Dict[str, Any]) -> BugReportValidator:
    """Validate bug report data and return validated model."""
    try:
        return BugReportValidator(**data)
    except Exception as e:
        raise ValidationError(f"Bug report validation failed: {e}")


def validate_developer_profile(data: Dict[str, Any]) -> DeveloperProfileValidator:
    """Validate developer profile data and return validated model."""
    try:
        return DeveloperProfileValidator(**data)
    except Exception as e:
        raise ValidationError(f"Developer profile validation failed: {e}")


def validate_developer_status(data: Dict[str, Any]) -> DeveloperStatusValidator:
    """Validate developer status data and return validated model."""
    try:
        return DeveloperStatusValidator(**data)
    except Exception as e:
        raise ValidationError(f"Developer status validation failed: {e}")


def validate_assignment(data: Dict[str, Any]) -> AssignmentValidator:
    """Validate assignment data and return validated model."""
    try:
        return AssignmentValidator(**data)
    except Exception as e:
        raise ValidationError(f"Assignment validation failed: {e}")


def validate_assignment_feedback(data: Dict[str, Any]) -> AssignmentFeedbackValidator:
    """Validate assignment feedback data and return validated model."""
    try:
        return AssignmentFeedbackValidator(**data)
    except Exception as e:
        raise ValidationError(f"Assignment feedback validation failed: {e}")


# Batch validation functions
def validate_multiple_bug_reports(data_list: List[Dict[str, Any]]) -> List[BugReportValidator]:
    """Validate multiple bug reports."""
    results = []
    errors = []
    
    for i, data in enumerate(data_list):
        try:
            results.append(validate_bug_report(data))
        except ValidationError as e:
            errors.append(f"Item {i}: {e}")
    
    if errors:
        raise ValidationError(f"Batch validation failed:\n" + "\n".join(errors))
    
    return results


def validate_multiple_developer_profiles(data_list: List[Dict[str, Any]]) -> List[DeveloperProfileValidator]:
    """Validate multiple developer profiles."""
    results = []
    errors = []
    
    for i, data in enumerate(data_list):
        try:
            results.append(validate_developer_profile(data))
        except ValidationError as e:
            errors.append(f"Item {i}: {e}")
    
    if errors:
        raise ValidationError(f"Batch validation failed:\n" + "\n".join(errors))
    
    return results