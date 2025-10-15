"""Data models for the notification system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from ..models.common import Assignment, BugReport, DeveloperProfile


class NotificationType(Enum):
    """Types of notifications."""
    BUG_ASSIGNMENT = "bug_assignment"
    ASSIGNMENT_UPDATE = "assignment_update"
    SYSTEM_ALERT = "system_alert"
    FEEDBACK_REQUEST = "feedback_request"
    WORKLOAD_WARNING = "workload_warning"


class NotificationChannel(Enum):
    """Available notification channels."""
    EMAIL = "email"
    SLACK = "slack"
    IN_APP = "in_app"


class NotificationStatus(Enum):
    """Notification delivery status."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class NotificationPreferences:
    """User notification preferences."""
    developer_id: str
    email_enabled: bool = True
    slack_enabled: bool = True
    in_app_enabled: bool = True
    channels_by_type: Dict[NotificationType, List[NotificationChannel]] = field(default_factory=dict)
    quiet_hours_start: Optional[str] = None  # HH:MM format
    quiet_hours_end: Optional[str] = None    # HH:MM format
    timezone: str = "UTC"
    
    def __post_init__(self):
        """Set default channel preferences if not provided."""
        if not self.channels_by_type:
            self.channels_by_type = {
                NotificationType.BUG_ASSIGNMENT: [NotificationChannel.EMAIL, NotificationChannel.SLACK],
                NotificationType.ASSIGNMENT_UPDATE: [NotificationChannel.SLACK],
                NotificationType.SYSTEM_ALERT: [NotificationChannel.EMAIL],
                NotificationType.FEEDBACK_REQUEST: [NotificationChannel.EMAIL],
                NotificationType.WORKLOAD_WARNING: [NotificationChannel.SLACK]
            }


@dataclass
class NotificationContext:
    """Context data for notification templates."""
    assignment: Optional[Assignment] = None
    bug_report: Optional[BugReport] = None
    developer: Optional[DeveloperProfile] = None
    assignment_reason: Optional[str] = None
    confidence_score: Optional[float] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationRequest:
    """Request to send a notification."""
    id: str
    notification_type: NotificationType
    recipient_id: str
    context: NotificationContext
    channels: List[NotificationChannel]
    priority: int = 1  # 1=high, 2=medium, 3=low
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NotificationResult:
    """Result of notification delivery attempt."""
    request_id: str
    channel: NotificationChannel
    status: NotificationStatus
    message: Optional[str] = None
    delivered_at: Optional[datetime] = None
    error_details: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None


@dataclass
class NotificationTemplate:
    """Template for generating notification content."""
    notification_type: NotificationType
    channel: NotificationChannel
    subject_template: str
    body_template: str
    format_type: str = "text"  # text, html, markdown
    
    def render_subject(self, context: NotificationContext) -> str:
        """Render the subject template with context data."""
        return self._render_template(self.subject_template, context)
    
    def render_body(self, context: NotificationContext) -> str:
        """Render the body template with context data."""
        return self._render_template(self.body_template, context)
    
    def _render_template(self, template: str, context: NotificationContext) -> str:
        """Render a template string with context data."""
        # Simple template rendering - in production, consider using Jinja2
        template_vars = {}
        
        if context.assignment:
            template_vars.update({
                'assignment_id': context.assignment.id,
                'bug_id': context.assignment.bug_id,
                'assigned_at': context.assignment.assigned_at.strftime('%Y-%m-%d %H:%M:%S'),
                'assignment_reason': context.assignment.assignment_reason,
                'confidence_score': context.assignment.confidence_score
            })
        
        if context.bug_report:
            template_vars.update({
                'bug_title': context.bug_report.title,
                'bug_description': context.bug_report.description[:200] + '...' if len(context.bug_report.description) > 200 else context.bug_report.description,
                'bug_reporter': context.bug_report.reporter,
                'bug_url': context.bug_report.url or f"Bug #{context.bug_report.id}",
                'bug_platform': context.bug_report.platform.upper(),
                'bug_created_at': context.bug_report.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        if context.developer:
            template_vars.update({
                'developer_name': context.developer.name,
                'developer_email': context.developer.email,
                'developer_skills': ', '.join(context.developer.skills)
            })
        
        if context.assignment_reason:
            template_vars['assignment_reason'] = context.assignment_reason
        
        if context.confidence_score:
            template_vars['confidence_score'] = f"{context.confidence_score:.1%}"
        
        # Add additional context data
        template_vars.update(context.additional_data)
        
        try:
            return template.format(**template_vars)
        except KeyError as e:
            # If template variable is missing, return template with placeholder
            return template.replace(f"{{{e.args[0]}}}", f"[{e.args[0]}]")


# Default notification templates
DEFAULT_TEMPLATES = {
    (NotificationType.BUG_ASSIGNMENT, NotificationChannel.EMAIL): NotificationTemplate(
        notification_type=NotificationType.BUG_ASSIGNMENT,
        channel=NotificationChannel.EMAIL,
        subject_template="New Bug Assignment: {bug_title}",
        body_template="""Hi {developer_name},

You have been assigned a new bug to work on:

Bug Details:
- Title: {bug_title}
- Platform: {bug_platform}
- Reporter: {bug_reporter}
- Created: {bug_created_at}
- URL: {bug_url}

Description:
{bug_description}

Assignment Details:
- Assigned: {assigned_at}
- Confidence: {confidence_score}
- Reason: {assignment_reason}

Please review the bug and start working on it when you have capacity.

Best regards,
Smart Bug Triage System""",
        format_type="text"
    ),
    
    (NotificationType.BUG_ASSIGNMENT, NotificationChannel.SLACK): NotificationTemplate(
        notification_type=NotificationType.BUG_ASSIGNMENT,
        channel=NotificationChannel.SLACK,
        subject_template="New Bug Assignment",
        body_template="""🐛 *New Bug Assignment for {developer_name}*

*{bug_title}*
Platform: {bug_platform} | Reporter: {bug_reporter}

📝 *Description:*
{bug_description}

🎯 *Assignment Details:*
• Confidence: {confidence_score}
• Reason: {assignment_reason}
• Link: {bug_url}

Happy debugging! 🔧""",
        format_type="markdown"
    ),
    
    (NotificationType.FEEDBACK_REQUEST, NotificationChannel.EMAIL): NotificationTemplate(
        notification_type=NotificationType.FEEDBACK_REQUEST,
        channel=NotificationChannel.EMAIL,
        subject_template="Feedback Request: Bug Assignment #{assignment_id}",
        body_template="""Hi {developer_name},

We'd love to get your feedback on a recent bug assignment:

Bug: {bug_title}
Assignment ID: {assignment_id}
Assigned: {assigned_at}

Please rate this assignment and help us improve our matching algorithm.

[Provide Feedback Link]

Thank you for your time!

Smart Bug Triage System""",
        format_type="text"
    )
}