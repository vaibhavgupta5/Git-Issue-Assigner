"""Email notification service implementation."""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
import logging
import asyncio
from datetime import datetime

from .base import NotificationService
from .models import (
    NotificationRequest,
    NotificationResult,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
    NotificationContext
)


class EmailNotificationService(NotificationService):
    """Email notification service using SMTP."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the email service.
        
        Args:
            config: Email configuration dictionary
        """
        super().__init__(NotificationChannel.EMAIL, config)
        
        self.smtp_host = config.get('smtp_host', 'smtp.gmail.com')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_username = config.get('smtp_username', '')
        self.smtp_password = config.get('smtp_password', '')
        self.smtp_use_tls = config.get('smtp_use_tls', True)
        self.from_address = config.get('email_from_address', '')
        self.from_name = config.get('email_from_name', 'Smart Bug Triage System')
        
        # Validate configuration
        if not self.validate_config():
            self.logger.error("Invalid email configuration")
            self._enabled = False
    
    def validate_config(self) -> bool:
        """Validate the email service configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        required_fields = ['smtp_host', 'smtp_username', 'smtp_password', 'email_from_address']
        missing_fields = []
        
        for field in required_fields:
            if not getattr(self, field.replace('email_', ''), None):
                missing_fields.append(field)
        
        if missing_fields:
            self.logger.error(f"Missing required email configuration fields: {missing_fields}")
            return False
        
        # Test SMTP connection
        try:
            self._test_smtp_connection()
            return True
        except Exception as e:
            self.logger.error(f"SMTP connection test failed: {e}")
            return False
    
    def _test_smtp_connection(self) -> None:
        """Test SMTP connection without sending email."""
        context = ssl.create_default_context()
        
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.smtp_use_tls:
                server.starttls(context=context)
            server.login(self.smtp_username, self.smtp_password)
    
    async def send_notification(
        self,
        request: NotificationRequest,
        template: NotificationTemplate,
        context: NotificationContext
    ) -> NotificationResult:
        """Send an email notification.
        
        Args:
            request: The notification request
            template: The email template to use
            context: Context data for the notification
            
        Returns:
            NotificationResult with delivery status
        """
        if not self.enabled:
            return self.create_result(
                request.id,
                NotificationStatus.FAILED,
                error_details="Email service is disabled"
            )
        
        try:
            # Get recipient email
            recipient_email = self._get_recipient_email(request.recipient_id, context)
            if not recipient_email:
                return self.create_result(
                    request.id,
                    NotificationStatus.FAILED,
                    error_details="Recipient email not found"
                )
            
            # Render email content
            subject = template.render_subject(context)
            body = template.render_body(context)
            
            # Create email message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_address}>"
            message["To"] = recipient_email
            
            # Add body
            if template.format_type == "html":
                part = MIMEText(body, "html")
            else:
                part = MIMEText(body, "plain")
            
            message.attach(part)
            
            # Send email
            await self._send_email_async(message, recipient_email)
            
            self.logger.info(f"Email sent successfully to {recipient_email} for request {request.id}")
            return self.create_result(
                request.id,
                NotificationStatus.SENT,
                message=f"Email sent to {recipient_email}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send email for request {request.id}: {e}")
            return self.create_result(
                request.id,
                NotificationStatus.FAILED,
                error_details=str(e)
            )
    
    def _get_recipient_email(self, recipient_id: str, context: NotificationContext) -> Optional[str]:
        """Get recipient email address.
        
        Args:
            recipient_id: The recipient ID
            context: Notification context
            
        Returns:
            Email address or None if not found
        """
        # Try to get email from developer profile in context
        if context.developer and context.developer.email:
            return context.developer.email
        
        # If no email in context, this would typically query the database
        # For now, we'll assume the recipient_id is an email or we have it in additional_data
        if '@' in recipient_id:
            return recipient_id
        
        # Check additional data
        return context.additional_data.get('recipient_email')
    
    async def _send_email_async(self, message: MIMEMultipart, recipient_email: str) -> None:
        """Send email asynchronously.
        
        Args:
            message: The email message to send
            recipient_email: Recipient email address
        """
        def _send_email():
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message, to_addrs=[recipient_email])
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_email)
    
    def get_delivery_status(self, message_id: str) -> NotificationStatus:
        """Get delivery status for a sent email.
        
        Args:
            message_id: The message ID
            
        Returns:
            Current delivery status
        """
        # SMTP doesn't provide delivery confirmation by default
        # This would require integration with email service providers' APIs
        # For now, we assume sent emails are delivered
        return NotificationStatus.DELIVERED
    
    def supports_delivery_confirmation(self) -> bool:
        """Check if this service supports delivery confirmation.
        
        Returns:
            True if delivery confirmation is supported
        """
        return False  # Basic SMTP doesn't support this