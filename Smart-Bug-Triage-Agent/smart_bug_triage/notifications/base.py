"""Base classes for notification services."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta

from .models import (
    NotificationRequest,
    NotificationResult,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
    NotificationContext
)


class NotificationService(ABC):
    """Abstract base class for notification services."""
    
    def __init__(self, channel: NotificationChannel, config: Dict[str, Any]):
        """Initialize the notification service.
        
        Args:
            channel: The notification channel this service handles
            config: Configuration dictionary for the service
        """
        self.channel = channel
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._enabled = config.get('enabled', True)
        self._max_retries = config.get('max_retries', 3)
        self._retry_delay = config.get('retry_delay', 60)  # seconds
    
    @property
    def enabled(self) -> bool:
        """Check if this notification service is enabled."""
        return self._enabled
    
    @abstractmethod
    async def send_notification(
        self,
        request: NotificationRequest,
        template: NotificationTemplate,
        context: NotificationContext
    ) -> NotificationResult:
        """Send a notification using this service.
        
        Args:
            request: The notification request
            template: The template to use for formatting
            context: Context data for the notification
            
        Returns:
            NotificationResult with delivery status
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate the service configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        pass
    
    def calculate_retry_delay(self, retry_count: int) -> int:
        """Calculate delay for retry attempt using exponential backoff.
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            Delay in seconds
        """
        return min(self._retry_delay * (2 ** retry_count), 3600)  # Max 1 hour
    
    def should_retry(self, result: NotificationResult) -> bool:
        """Determine if a failed notification should be retried.
        
        Args:
            result: The notification result
            
        Returns:
            True if should retry, False otherwise
        """
        return (
            result.status == NotificationStatus.FAILED and
            result.retry_count < self._max_retries and
            self._is_retryable_error(result.error_details)
        )
    
    def _is_retryable_error(self, error_details: Optional[str]) -> bool:
        """Check if an error is retryable.
        
        Args:
            error_details: Error details string
            
        Returns:
            True if error is retryable, False otherwise
        """
        if not error_details:
            return True
        
        # Common retryable errors
        retryable_errors = [
            'timeout',
            'connection',
            'network',
            'rate limit',
            'server error',
            '5xx',
            'temporary'
        ]
        
        error_lower = error_details.lower()
        return any(error in error_lower for error in retryable_errors)
    
    def create_result(
        self,
        request_id: str,
        status: NotificationStatus,
        message: Optional[str] = None,
        error_details: Optional[str] = None,
        retry_count: int = 0
    ) -> NotificationResult:
        """Create a notification result.
        
        Args:
            request_id: The notification request ID
            status: Delivery status
            message: Success message
            error_details: Error details if failed
            retry_count: Current retry count
            
        Returns:
            NotificationResult instance
        """
        result = NotificationResult(
            request_id=request_id,
            channel=self.channel,
            status=status,
            message=message,
            error_details=error_details,
            retry_count=retry_count
        )
        
        if status == NotificationStatus.SENT:
            result.delivered_at = datetime.utcnow()
        elif status == NotificationStatus.FAILED and self.should_retry(result):
            result.status = NotificationStatus.RETRYING
            delay = self.calculate_retry_delay(retry_count)
            result.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        
        return result


class NotificationServiceRegistry:
    """Registry for notification services."""
    
    def __init__(self):
        """Initialize the registry."""
        self._services: Dict[NotificationChannel, NotificationService] = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def register_service(self, service: NotificationService) -> None:
        """Register a notification service.
        
        Args:
            service: The notification service to register
        """
        if not service.validate_config():
            self.logger.warning(f"Service {service.channel} has invalid configuration, skipping registration")
            return
        
        self._services[service.channel] = service
        self.logger.info(f"Registered notification service for channel: {service.channel}")
    
    def get_service(self, channel: NotificationChannel) -> Optional[NotificationService]:
        """Get a notification service by channel.
        
        Args:
            channel: The notification channel
            
        Returns:
            NotificationService instance or None if not found
        """
        return self._services.get(channel)
    
    def get_enabled_services(self) -> List[NotificationService]:
        """Get all enabled notification services.
        
        Returns:
            List of enabled notification services
        """
        return [service for service in self._services.values() if service.enabled]
    
    def get_available_channels(self) -> List[NotificationChannel]:
        """Get list of available notification channels.
        
        Returns:
            List of available channels
        """
        return [channel for channel, service in self._services.items() if service.enabled]