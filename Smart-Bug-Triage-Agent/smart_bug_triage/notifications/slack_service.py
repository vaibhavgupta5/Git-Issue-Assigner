"""Slack notification service implementation."""

import json
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List
import logging
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


class SlackNotificationService(NotificationService):
    """Slack notification service using Bot API and Webhooks."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Slack service.
        
        Args:
            config: Slack configuration dictionary
        """
        super().__init__(NotificationChannel.SLACK, config)
        
        self.bot_token = config.get('slack_bot_token', '')
        self.webhook_url = config.get('slack_webhook_url', '')
        self.default_channel = config.get('slack_default_channel', '#bug-triage')
        self.mention_users = config.get('slack_mention_users', True)
        
        # API endpoints
        self.api_base_url = "https://slack.com/api"
        self.post_message_url = f"{self.api_base_url}/chat.postMessage"
        self.users_lookup_url = f"{self.api_base_url}/users.lookupByEmail"
        
        # Validate configuration
        if not self.validate_config():
            self.logger.error("Invalid Slack configuration")
            self._enabled = False
    
    def validate_config(self) -> bool:
        """Validate the Slack service configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        # Need either bot token or webhook URL
        if not self.bot_token and not self.webhook_url:
            self.logger.error("Either Slack bot token or webhook URL is required")
            return False
        
        # If using bot token, validate it
        if self.bot_token:
            try:
                # This would test the token in a real implementation
                return True
            except Exception as e:
                self.logger.error(f"Slack bot token validation failed: {e}")
                return False
        
        return True
    
    async def send_notification(
        self,
        request: NotificationRequest,
        template: NotificationTemplate,
        context: NotificationContext
    ) -> NotificationResult:
        """Send a Slack notification.
        
        Args:
            request: The notification request
            template: The Slack template to use
            context: Context data for the notification
            
        Returns:
            NotificationResult with delivery status
        """
        if not self.enabled:
            return self.create_result(
                request.id,
                NotificationStatus.FAILED,
                error_details="Slack service is disabled"
            )
        
        try:
            # Determine channel and user
            channel = await self._get_notification_channel(request.recipient_id, context)
            user_mention = await self._get_user_mention(request.recipient_id, context)
            
            # Render message content
            subject = template.render_subject(context)
            body = template.render_body(context)
            
            # Add user mention if enabled and available
            if self.mention_users and user_mention:
                body = f"{user_mention}\n\n{body}"
            
            # Create Slack message payload
            message_payload = self._create_message_payload(
                channel=channel,
                text=subject,
                blocks=self._create_message_blocks(subject, body, context),
                context=context
            )
            
            # Send message
            if self.bot_token:
                result = await self._send_via_bot_api(message_payload)
            else:
                result = await self._send_via_webhook(message_payload)
            
            if result:
                self.logger.info(f"Slack message sent successfully to {channel} for request {request.id}")
                return self.create_result(
                    request.id,
                    NotificationStatus.SENT,
                    message=f"Slack message sent to {channel}"
                )
            else:
                return self.create_result(
                    request.id,
                    NotificationStatus.FAILED,
                    error_details="Failed to send Slack message"
                )
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack notification for request {request.id}: {e}")
            return self.create_result(
                request.id,
                NotificationStatus.FAILED,
                error_details=str(e)
            )
    
    async def _get_notification_channel(self, recipient_id: str, context: NotificationContext) -> str:
        """Get the Slack channel for the notification.
        
        Args:
            recipient_id: The recipient ID
            context: Notification context
            
        Returns:
            Slack channel (e.g., #channel or @user)
        """
        # Check if recipient_id is already a channel
        if recipient_id.startswith('#') or recipient_id.startswith('@'):
            return recipient_id
        
        # Try to get user's Slack handle from context
        if context.developer and hasattr(context.developer, 'slack_handle'):
            return f"@{context.developer.slack_handle}"
        
        # Check additional data for Slack channel
        slack_channel = context.additional_data.get('slack_channel')
        if slack_channel:
            return slack_channel
        
        # Default to configured channel
        return self.default_channel
    
    async def _get_user_mention(self, recipient_id: str, context: NotificationContext) -> Optional[str]:
        """Get Slack user mention string.
        
        Args:
            recipient_id: The recipient ID
            context: Notification context
            
        Returns:
            Slack user mention or None
        """
        if not self.mention_users or not self.bot_token:
            return None
        
        try:
            # Try to get user by email
            email = None
            if context.developer and context.developer.email:
                email = context.developer.email
            elif '@' in recipient_id:
                email = recipient_id
            
            if email:
                user_id = await self._lookup_user_by_email(email)
                if user_id:
                    return f"<@{user_id}>"
            
        except Exception as e:
            self.logger.warning(f"Failed to lookup Slack user: {e}")
        
        return None
    
    async def _lookup_user_by_email(self, email: str) -> Optional[str]:
        """Look up Slack user ID by email.
        
        Args:
            email: User email address
            
        Returns:
            Slack user ID or None
        """
        headers = {
            'Authorization': f'Bearer {self.bot_token}',
            'Content-Type': 'application/json'
        }
        
        params = {'email': email}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(self.users_lookup_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('ok') and data.get('user'):
                        return data['user']['id']
        
        return None
    
    def _create_message_payload(
        self,
        channel: str,
        text: str,
        blocks: List[Dict[str, Any]],
        context: NotificationContext
    ) -> Dict[str, Any]:
        """Create Slack message payload.
        
        Args:
            channel: Target channel
            text: Fallback text
            blocks: Message blocks
            context: Notification context
            
        Returns:
            Message payload dictionary
        """
        payload = {
            'channel': channel,
            'text': text,
            'blocks': blocks,
            'unfurl_links': False,
            'unfurl_media': False
        }
        
        # Add thread timestamp if this is a reply
        thread_ts = context.additional_data.get('thread_ts')
        if thread_ts:
            payload['thread_ts'] = thread_ts
        
        return payload
    
    def _create_message_blocks(
        self,
        subject: str,
        body: str,
        context: NotificationContext
    ) -> List[Dict[str, Any]]:
        """Create Slack message blocks for rich formatting.
        
        Args:
            subject: Message subject
            body: Message body
            context: Notification context
            
        Returns:
            List of Slack block elements
        """
        blocks = []
        
        # Header block
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": subject
            }
        })
        
        # Main content block
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": body
            }
        })
        
        # Add action buttons if this is a bug assignment
        if context.assignment and context.bug_report:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Bug"
                        },
                        "url": context.bug_report.url,
                        "style": "primary"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Provide Feedback"
                        },
                        "value": f"feedback_{context.assignment.id}",
                        "action_id": "assignment_feedback"
                    }
                ]
            })
        
        # Add divider
        blocks.append({"type": "divider"})
        
        return blocks
    
    async def _send_via_bot_api(self, payload: Dict[str, Any]) -> bool:
        """Send message via Slack Bot API.
        
        Args:
            payload: Message payload
            
        Returns:
            True if successful, False otherwise
        """
        headers = {
            'Authorization': f'Bearer {self.bot_token}',
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.post_message_url,
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('ok', False)
                else:
                    self.logger.error(f"Slack API error: {response.status}")
                    return False
    
    async def _send_via_webhook(self, payload: Dict[str, Any]) -> bool:
        """Send message via Slack Webhook.
        
        Args:
            payload: Message payload
            
        Returns:
            True if successful, False otherwise
        """
        # Webhooks use a simpler payload format
        webhook_payload = {
            'text': payload.get('text', ''),
            'blocks': payload.get('blocks', [])
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.webhook_url,
                json=webhook_payload
            ) as response:
                return response.status == 200
    
    def supports_delivery_confirmation(self) -> bool:
        """Check if this service supports delivery confirmation.
        
        Returns:
            True if delivery confirmation is supported
        """
        return bool(self.bot_token)  # Bot API provides better delivery info
    
    async def get_message_status(self, channel: str, timestamp: str) -> NotificationStatus:
        """Get message delivery status.
        
        Args:
            channel: Slack channel
            timestamp: Message timestamp
            
        Returns:
            Current delivery status
        """
        if not self.bot_token:
            return NotificationStatus.DELIVERED  # Assume delivered for webhooks
        
        # In a real implementation, this would check message status via API
        return NotificationStatus.DELIVERED