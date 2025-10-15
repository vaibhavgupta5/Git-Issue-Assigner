"""Notification system for bug assignments and system events."""

from .base import NotificationService, NotificationChannel, NotificationTemplate
from .email_service import EmailNotificationService
from .slack_service import SlackNotificationService
from .notification_manager import NotificationManager
from .models import (
    NotificationRequest,
    NotificationResult,
    NotificationPreferences,
    NotificationStatus,
    NotificationType,
    NotificationContext
)

__all__ = [
    'NotificationService',
    'NotificationChannel',
    'NotificationTemplate',
    'EmailNotificationService',
    'SlackNotificationService',
    'NotificationManager',
    'NotificationRequest',
    'NotificationResult',
    'NotificationPreferences',
    'NotificationStatus',
    'NotificationType',
    'NotificationContext'
]