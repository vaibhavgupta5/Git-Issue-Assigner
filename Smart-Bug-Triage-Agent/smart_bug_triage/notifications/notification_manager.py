"""Notification manager for coordinating notification delivery."""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
import uuid
from dataclasses import asdict

from .base import NotificationServiceRegistry
from .email_service import EmailNotificationService
from .slack_service import SlackNotificationService
from .models import (
    NotificationRequest,
    NotificationResult,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    NotificationPreferences,
    NotificationTemplate,
    NotificationContext,
    DEFAULT_TEMPLATES
)
from ..config.settings import NotificationConfig
from ..database.connection import DatabaseManager


class NotificationManager:
    """Manages notification delivery across multiple channels."""
    
    def __init__(self, config: NotificationConfig, db_manager: DatabaseManager):
        """Initialize the notification manager.
        
        Args:
            config: Notification configuration
            db_manager: Database manager for persistence
        """
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Service registry
        self.service_registry = NotificationServiceRegistry()
        
        # Template storage
        self.templates: Dict[tuple, NotificationTemplate] = DEFAULT_TEMPLATES.copy()
        
        # Retry queue
        self.retry_queue: List[NotificationRequest] = []
        self.retry_task: Optional[asyncio.Task] = None
        
        # Preferences cache
        self.preferences_cache: Dict[str, NotificationPreferences] = {}
        self.cache_ttl = timedelta(minutes=30)
        self.cache_timestamps: Dict[str, datetime] = {}
        
        # Initialize services
        self._initialize_services()
        
        # Start retry processor
        if self.config.enabled:
            self._start_retry_processor()
    
    def _initialize_services(self) -> None:
        """Initialize notification services based on configuration."""
        if not self.config.enabled:
            self.logger.info("Notifications are disabled")
            return
        
        # Initialize email service
        if self.config.email_enabled:
            email_config = {
                'enabled': True,
                'smtp_host': self.config.smtp_host,
                'smtp_port': self.config.smtp_port,
                'smtp_username': self.config.smtp_username,
                'smtp_password': self.config.smtp_password,
                'smtp_use_tls': self.config.smtp_use_tls,
                'email_from_address': self.config.email_from_address,
                'email_from_name': self.config.email_from_name,
                'max_retries': self.config.max_retries,
                'retry_delay': self.config.retry_delay
            }
            
            email_service = EmailNotificationService(email_config)
            self.service_registry.register_service(email_service)
        
        # Initialize Slack service
        if self.config.slack_enabled:
            slack_config = {
                'enabled': True,
                'slack_bot_token': self.config.slack_bot_token,
                'slack_webhook_url': self.config.slack_webhook_url,
                'slack_default_channel': self.config.slack_default_channel,
                'slack_mention_users': self.config.slack_mention_users,
                'max_retries': self.config.max_retries,
                'retry_delay': self.config.retry_delay
            }
            
            slack_service = SlackNotificationService(slack_config)
            self.service_registry.register_service(slack_service)
        
        self.logger.info(f"Initialized {len(self.service_registry.get_enabled_services())} notification services")
    
    async def send_notification(
        self,
        notification_type: NotificationType,
        recipient_id: str,
        context: NotificationContext,
        channels: Optional[List[NotificationChannel]] = None,
        priority: int = 1
    ) -> List[NotificationResult]:
        """Send a notification to specified channels.
        
        Args:
            notification_type: Type of notification
            recipient_id: ID of the recipient
            context: Context data for the notification
            channels: Specific channels to use (optional)
            priority: Notification priority (1=high, 2=medium, 3=low)
            
        Returns:
            List of notification results
        """
        if not self.config.enabled:
            self.logger.debug("Notifications are disabled, skipping")
            return []
        
        # Get user preferences
        preferences = await self.get_user_preferences(recipient_id)
        
        # Determine channels to use
        if channels is None:
            channels = preferences.channels_by_type.get(notification_type, [])
        
        # Filter channels based on user preferences
        enabled_channels = self._filter_enabled_channels(channels, preferences)
        
        if not enabled_channels:
            self.logger.info(f"No enabled channels for {notification_type} to {recipient_id}")
            return []
        
        # Check quiet hours
        if self._is_quiet_hours(preferences):
            if priority > 1:  # Only high priority notifications during quiet hours
                self.logger.info(f"Skipping {notification_type} to {recipient_id} due to quiet hours")
                return []
        
        # Create notification request
        request = NotificationRequest(
            id=str(uuid.uuid4()),
            notification_type=notification_type,
            recipient_id=recipient_id,
            context=context,
            channels=enabled_channels,
            priority=priority
        )
        
        # Send to each channel
        results = []
        for channel in enabled_channels:
            result = await self._send_to_channel(request, channel)
            results.append(result)
            
            # Store result in database
            self._store_notification_result(result)
            
            # Add to retry queue if needed
            if result.status == NotificationStatus.RETRYING:
                self.retry_queue.append(request)
        
        return results
    
    async def _send_to_channel(
        self,
        request: NotificationRequest,
        channel: NotificationChannel
    ) -> NotificationResult:
        """Send notification to a specific channel.
        
        Args:
            request: Notification request
            channel: Target channel
            
        Returns:
            Notification result
        """
        # Get service for channel
        service = self.service_registry.get_service(channel)
        if not service or not service.enabled:
            return NotificationResult(
                request_id=request.id,
                channel=channel,
                status=NotificationStatus.FAILED,
                error_details=f"Service for {channel} not available"
            )
        
        # Get template
        template = self.get_template(request.notification_type, channel)
        if not template:
            return NotificationResult(
                request_id=request.id,
                channel=channel,
                status=NotificationStatus.FAILED,
                error_details=f"Template for {request.notification_type}/{channel} not found"
            )
        
        # Send notification
        try:
            result = await service.send_notification(request, template, request.context)
            self.logger.info(f"Notification {request.id} sent via {channel}: {result.status}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to send notification {request.id} via {channel}: {e}")
            return NotificationResult(
                request_id=request.id,
                channel=channel,
                status=NotificationStatus.FAILED,
                error_details=str(e)
            )
    
    def _filter_enabled_channels(
        self,
        channels: List[NotificationChannel],
        preferences: NotificationPreferences
    ) -> List[NotificationChannel]:
        """Filter channels based on user preferences and service availability.
        
        Args:
            channels: Requested channels
            preferences: User preferences
            
        Returns:
            List of enabled channels
        """
        enabled_channels = []
        available_channels = self.service_registry.get_available_channels()
        
        for channel in channels:
            # Check if service is available
            if channel not in available_channels:
                continue
            
            # Check user preferences
            if channel == NotificationChannel.EMAIL and not preferences.email_enabled:
                continue
            elif channel == NotificationChannel.SLACK and not preferences.slack_enabled:
                continue
            elif channel == NotificationChannel.IN_APP and not preferences.in_app_enabled:
                continue
            
            enabled_channels.append(channel)
        
        return enabled_channels
    
    def _is_quiet_hours(self, preferences: NotificationPreferences) -> bool:
        """Check if current time is within user's quiet hours.
        
        Args:
            preferences: User notification preferences
            
        Returns:
            True if in quiet hours, False otherwise
        """
        if not self.config.quiet_hours_enabled:
            return False
        
        if not preferences.quiet_hours_start or not preferences.quiet_hours_end:
            return False
        
        # This is a simplified implementation
        # In production, you'd want proper timezone handling
        now = datetime.now().time()
        start_time = datetime.strptime(preferences.quiet_hours_start, "%H:%M").time()
        end_time = datetime.strptime(preferences.quiet_hours_end, "%H:%M").time()
        
        if start_time <= end_time:
            return start_time <= now <= end_time
        else:  # Quiet hours span midnight
            return now >= start_time or now <= end_time
    
    async def get_user_preferences(self, user_id: str) -> NotificationPreferences:
        """Get user notification preferences with caching.
        
        Args:
            user_id: User ID
            
        Returns:
            User notification preferences
        """
        # Check cache
        if user_id in self.preferences_cache:
            cache_time = self.cache_timestamps.get(user_id)
            if cache_time and datetime.utcnow() - cache_time < self.cache_ttl:
                return self.preferences_cache[user_id]
        
        # Load from database
        preferences = self._load_user_preferences(user_id)
        
        # Cache the result
        self.preferences_cache[user_id] = preferences
        self.cache_timestamps[user_id] = datetime.utcnow()
        
        return preferences
    
    def _load_user_preferences(self, user_id: str) -> NotificationPreferences:
        """Load user preferences from database.
        
        Args:
            user_id: User ID
            
        Returns:
            User notification preferences
        """
        try:
            query = """
                SELECT * FROM notification_preferences 
                WHERE developer_id = :user_id
            """
            
            with self.db.get_session() as session:
                from sqlalchemy import text
                result = session.execute(text(query), {"user_id": user_id})
                row = result.fetchone()
                
                if row:
                    # Convert database row to preferences object
                    return NotificationPreferences(
                        developer_id=row.developer_id,
                        email_enabled=row.email_enabled,
                        slack_enabled=row.slack_enabled,
                        in_app_enabled=row.in_app_enabled,
                        channels_by_type=row.channels_by_type or {},
                        quiet_hours_start=row.quiet_hours_start,
                        quiet_hours_end=row.quiet_hours_end,
                        timezone=row.timezone or 'UTC'
                    )
        except Exception as e:
            self.logger.warning(f"Failed to load preferences for {user_id}: {e}")
        
        # Return default preferences
        return NotificationPreferences(
            developer_id=user_id,
            quiet_hours_start=self.config.default_quiet_hours_start,
            quiet_hours_end=self.config.default_quiet_hours_end,
            timezone=self.config.default_timezone
        )
    
    def update_user_preferences(
        self,
        user_id: str,
        preferences: NotificationPreferences
    ) -> bool:
        """Update user notification preferences.
        
        Args:
            user_id: User ID
            preferences: New preferences
            
        Returns:
            True if successful, False otherwise
        """
        try:
            query = """
                INSERT INTO notification_preferences 
                (developer_id, email_enabled, slack_enabled, in_app_enabled, 
                 channels_by_type, quiet_hours_start, quiet_hours_end, timezone)
                VALUES (:developer_id, :email_enabled, :slack_enabled, :in_app_enabled, 
                        :channels_by_type, :quiet_hours_start, :quiet_hours_end, :timezone)
                ON CONFLICT (developer_id) DO UPDATE SET
                    email_enabled = EXCLUDED.email_enabled,
                    slack_enabled = EXCLUDED.slack_enabled,
                    in_app_enabled = EXCLUDED.in_app_enabled,
                    channels_by_type = EXCLUDED.channels_by_type,
                    quiet_hours_start = EXCLUDED.quiet_hours_start,
                    quiet_hours_end = EXCLUDED.quiet_hours_end,
                    timezone = EXCLUDED.timezone,
                    updated_at = NOW()
            """
            
            with self.db.get_session() as session:
                from sqlalchemy import text
                session.execute(text(query), {
                    'developer_id': preferences.developer_id,
                    'email_enabled': preferences.email_enabled,
                    'slack_enabled': preferences.slack_enabled,
                    'in_app_enabled': preferences.in_app_enabled,
                    'channels_by_type': preferences.channels_by_type,
                    'quiet_hours_start': preferences.quiet_hours_start,
                    'quiet_hours_end': preferences.quiet_hours_end,
                    'timezone': preferences.timezone
                })
            
            # Update cache
            self.preferences_cache[user_id] = preferences
            self.cache_timestamps[user_id] = datetime.utcnow()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update preferences for {user_id}: {e}")
            return False
    
    def get_template(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel
    ) -> Optional[NotificationTemplate]:
        """Get notification template for type and channel.
        
        Args:
            notification_type: Type of notification
            channel: Target channel
            
        Returns:
            Notification template or None if not found
        """
        return self.templates.get((notification_type, channel))
    
    def register_template(self, template: NotificationTemplate) -> None:
        """Register a custom notification template.
        
        Args:
            template: Template to register
        """
        key = (template.notification_type, template.channel)
        self.templates[key] = template
        self.logger.info(f"Registered template for {template.notification_type}/{template.channel}")
    
    def _store_notification_result(self, result: NotificationResult) -> None:
        """Store notification result in database.
        
        Args:
            result: Notification result to store
        """
        try:
            query = """
                INSERT INTO notification_results 
                (request_id, channel, status, message, delivered_at, 
                 error_details, retry_count, next_retry_at)
                VALUES (:request_id, :channel, :status, :message, :delivered_at, 
                        :error_details, :retry_count, :next_retry_at)
            """
            
            with self.db.get_session() as session:
                from sqlalchemy import text
                session.execute(text(query), {
                    'request_id': result.request_id,
                    'channel': result.channel.value,
                    'status': result.status.value,
                    'message': result.message,
                    'delivered_at': result.delivered_at,
                    'error_details': result.error_details,
                    'retry_count': result.retry_count,
                    'next_retry_at': result.next_retry_at
                })
                    
        except Exception as e:
            self.logger.error(f"Failed to store notification result: {e}")
    
    def _start_retry_processor(self) -> None:
        """Start the retry processor task."""
        if self.retry_task is None or self.retry_task.done():
            self.retry_task = asyncio.create_task(self._process_retries())
    
    async def _process_retries(self) -> None:
        """Process notification retries."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                if not self.retry_queue:
                    continue
                
                # Process retry queue
                current_time = datetime.utcnow()
                ready_for_retry = []
                
                for request in self.retry_queue[:]:
                    # Check if it's time to retry
                    # This is simplified - in production you'd track retry times per request
                    ready_for_retry.append(request)
                    self.retry_queue.remove(request)
                
                # Retry notifications
                for request in ready_for_retry:
                    for channel in request.channels:
                        result = await self._send_to_channel(request, channel)
                        self._store_notification_result(result)
                        
                        if result.status == NotificationStatus.RETRYING:
                            self.retry_queue.append(request)
                
            except Exception as e:
                self.logger.error(f"Error in retry processor: {e}")
                await asyncio.sleep(60)
    
    def get_notification_stats(self, days: int = 7) -> Dict[str, int]:
        """Get notification delivery statistics.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary with statistics
        """
        try:
            query = """
                SELECT 
                    channel,
                    status,
                    COUNT(*) as count
                FROM notification_results 
                WHERE delivered_at >= NOW() - INTERVAL ':days days'
                GROUP BY channel, status
            """
            
            stats = {}
            with self.db.get_session() as session:
                from sqlalchemy import text
                result = session.execute(text(query), {'days': days})
                rows = result.fetchall()
                
                for row in rows:
                    key = f"{row.channel}_{row.status}"
                    stats[key] = row.count
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get notification stats: {e}")
            return {}
    
    async def shutdown(self) -> None:
        """Shutdown the notification manager."""
        if self.retry_task and not self.retry_task.done():
            self.retry_task.cancel()
            try:
                await self.retry_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Notification manager shutdown complete")