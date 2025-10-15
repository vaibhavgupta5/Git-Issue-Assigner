"""Message publisher for sending messages to queues."""

import logging
import time
from typing import Any, Optional, Dict
from datetime import datetime

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from .connection import MessageQueueConnection
from .serialization import MessageSerializer, MessageType, MessageValidator
from ..config.settings import MessageQueueConfig


logger = logging.getLogger(__name__)


class MessagePublisher:
    """Base class for publishing messages to RabbitMQ queues."""
    
    def __init__(self, connection: MessageQueueConnection):
        """Initialize publisher with connection.
        
        Args:
            connection: Message queue connection instance
        """
        self.connection = connection
        self.config = connection.config
        self._publish_stats = {
            'total_published': 0,
            'failed_publishes': 0,
            'last_publish_time': None
        }
    
    def publish_message(
        self,
        message: Any,
        message_type: MessageType,
        routing_key: str,
        priority: int = 0,
        expiration: Optional[int] = None,
        retry_count: int = 3
    ) -> bool:
        """Publish a message to the exchange.
        
        Args:
            message: Message object to publish
            message_type: Type of the message
            routing_key: Routing key for message delivery
            priority: Message priority (0-255)
            expiration: Message TTL in milliseconds
            retry_count: Number of retry attempts
            
        Returns:
            True if message published successfully, False otherwise
        """
        for attempt in range(retry_count + 1):
            try:
                # Serialize message
                serialized_data = MessageSerializer.serialize(message, message_type)
                
                # Prepare message properties
                properties = pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    priority=priority,
                    timestamp=int(time.time()),
                    message_id=self._generate_message_id(),
                    content_type='application/json',
                    content_encoding='utf-8'
                )
                
                if expiration:
                    properties.expiration = str(expiration)
                
                # Publish message
                with self.connection.channel_context() as channel:
                    channel.basic_publish(
                        exchange=self.config.exchange_name,
                        routing_key=routing_key,
                        body=serialized_data,
                        properties=properties,
                        mandatory=True  # Return message if no queue bound
                    )
                
                # Update statistics
                self._publish_stats['total_published'] += 1
                self._publish_stats['last_publish_time'] = datetime.utcnow()
                
                logger.debug(f"Published message of type {message_type.value} with routing key {routing_key}")
                return True
                
            except (AMQPConnectionError, AMQPChannelError) as e:
                logger.warning(f"Connection error on publish attempt {attempt + 1}: {e}")
                if attempt < retry_count:
                    # Try to reconnect
                    self.connection.reconnect_with_backoff(max_retries=2)
                    time.sleep(0.5 * (attempt + 1))  # Brief delay between retries
                else:
                    logger.error(f"Failed to publish message after {retry_count + 1} attempts")
                    self._publish_stats['failed_publishes'] += 1
                    return False
                    
            except Exception as e:
                logger.error(f"Unexpected error publishing message: {e}")
                self._publish_stats['failed_publishes'] += 1
                return False
        
        return False
    
    def publish_bug_report(self, bug_report: Any) -> bool:
        """Publish a new bug report.
        
        Args:
            bug_report: Bug report object
            
        Returns:
            True if published successfully, False otherwise
        """
        return self.publish_message(
            message=bug_report,
            message_type=MessageType.BUG_REPORT,
            routing_key="bug_triage.new_bugs",
            priority=5
        )
    
    def publish_categorized_bug(self, categorized_bug: Any) -> bool:
        """Publish a categorized bug for assignment.
        
        Args:
            categorized_bug: Categorized bug object
            
        Returns:
            True if published successfully, False otherwise
        """
        # Higher priority for critical bugs
        priority = 10 if hasattr(categorized_bug, 'severity') and categorized_bug.severity == 'Critical' else 5
        
        return self.publish_message(
            message=categorized_bug,
            message_type=MessageType.CATEGORIZED_BUG,
            routing_key="bug_triage.triaged_bugs",
            priority=priority
        )
    
    def publish_assignment(self, assignment: Any) -> bool:
        """Publish a bug assignment.
        
        Args:
            assignment: Assignment object
            
        Returns:
            True if published successfully, False otherwise
        """
        return self.publish_message(
            message=assignment,
            message_type=MessageType.ASSIGNMENT,
            routing_key="bug_triage.assignments",
            priority=7
        )
    
    def publish_notification(self, notification: Any) -> bool:
        """Publish a notification message.
        
        Args:
            notification: Notification object
            
        Returns:
            True if published successfully, False otherwise
        """
        return self.publish_message(
            message=notification,
            message_type=MessageType.NOTIFICATION,
            routing_key="bug_triage.notifications",
            priority=3
        )
    
    def publish_developer_status_update(self, status_update: Any) -> bool:
        """Publish a developer status update.
        
        Args:
            status_update: Developer status update object
            
        Returns:
            True if published successfully, False otherwise
        """
        return self.publish_message(
            message=status_update,
            message_type=MessageType.DEVELOPER_STATUS_UPDATE,
            routing_key="bug_triage.developer_status",
            priority=2
        )
    
    def publish_system_event(self, event: Any, priority: int = 1) -> bool:
        """Publish a system event.
        
        Args:
            event: System event object
            priority: Event priority
            
        Returns:
            True if published successfully, False otherwise
        """
        return self.publish_message(
            message=event,
            message_type=MessageType.SYSTEM_EVENT,
            routing_key="bug_triage.system_events",
            priority=priority
        )
    
    def publish_batch(self, messages: list, routing_key: str) -> Dict[str, int]:
        """Publish multiple messages in a batch.
        
        Args:
            messages: List of (message, message_type) tuples
            routing_key: Routing key for all messages
            
        Returns:
            Dictionary with success and failure counts
        """
        results = {'success': 0, 'failed': 0}
        
        try:
            with self.connection.channel_context() as channel:
                for message, message_type in messages:
                    try:
                        serialized_data = MessageSerializer.serialize(message, message_type)
                        
                        properties = pika.BasicProperties(
                            delivery_mode=2,
                            timestamp=int(time.time()),
                            message_id=self._generate_message_id(),
                            content_type='application/json'
                        )
                        
                        channel.basic_publish(
                            exchange=self.config.exchange_name,
                            routing_key=routing_key,
                            body=serialized_data,
                            properties=properties
                        )
                        
                        results['success'] += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to publish message in batch: {e}")
                        results['failed'] += 1
                        
        except Exception as e:
            logger.error(f"Batch publish failed: {e}")
            results['failed'] = len(messages) - results['success']
        
        self._publish_stats['total_published'] += results['success']
        self._publish_stats['failed_publishes'] += results['failed']
        
        return results
    
    def _generate_message_id(self) -> str:
        """Generate unique message ID.
        
        Returns:
            Unique message identifier
        """
        import random
        timestamp = int(time.time() * 1000000)  # Microsecond precision
        random_suffix = random.randint(1000, 9999)
        return f"msg_{timestamp}_{random_suffix}"
    
    def get_publish_stats(self) -> Dict[str, Any]:
        """Get publishing statistics.
        
        Returns:
            Dictionary with publishing statistics
        """
        stats = self._publish_stats.copy()
        
        # Calculate success rate
        total = stats['total_published'] + stats['failed_publishes']
        if total > 0:
            stats['success_rate'] = stats['total_published'] / total
        else:
            stats['success_rate'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset publishing statistics."""
        self._publish_stats = {
            'total_published': 0,
            'failed_publishes': 0,
            'last_publish_time': None
        }