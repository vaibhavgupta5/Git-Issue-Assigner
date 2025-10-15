"""Dead letter queue handling for failed messages."""

import logging
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from .connection import MessageQueueConnection
from .consumer import MessageConsumer, MessageHandler
from .publisher import MessagePublisher
from .serialization import MessageDeserializer, MessageType


logger = logging.getLogger(__name__)


@dataclass
class FailedMessage:
    """Represents a failed message in the dead letter queue."""
    original_queue: str
    message_type: MessageType
    message_data: Any
    failure_reason: str
    failure_count: int
    first_failed_at: datetime
    last_failed_at: datetime
    original_routing_key: str
    original_properties: Dict[str, Any]


class DeadLetterHandler(MessageHandler):
    """Handles messages in dead letter queues."""
    
    def __init__(self, connection: MessageQueueConnection, publisher: MessagePublisher):
        """Initialize dead letter handler.
        
        Args:
            connection: Message queue connection
            publisher: Message publisher for requeuing
        """
        self.connection = connection
        self.publisher = publisher
        self.config = connection.config
        self._retry_strategies: Dict[MessageType, Callable] = {}
        self._max_retry_attempts = 3
        self._retry_delay_minutes = [5, 15, 60]  # Progressive delay
    
    def handle_message(self, message_data: Any, message_type: MessageType, delivery_tag: str) -> bool:
        """Handle a message from the dead letter queue.
        
        Args:
            message_data: Deserialized message data
            message_type: Type of the message
            delivery_tag: Delivery tag for acknowledgment
            
        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            # Parse failed message information
            failed_message = self._parse_failed_message(message_data, message_type)
            
            if not failed_message:
                logger.error(f"Could not parse failed message {delivery_tag}")
                return False
            
            # Determine if message should be retried
            if self._should_retry_message(failed_message):
                return self._retry_message(failed_message)
            else:
                return self._handle_permanently_failed_message(failed_message)
                
        except Exception as e:
            logger.error(f"Error handling dead letter message {delivery_tag}: {e}")
            return False
    
    def get_supported_message_types(self) -> List[MessageType]:
        """Get list of message types this handler supports.
        
        Returns:
            List of all message types (handles any failed message)
        """
        return list(MessageType)
    
    def register_retry_strategy(self, message_type: MessageType, strategy: Callable[[FailedMessage], bool]) -> None:
        """Register a custom retry strategy for a message type.
        
        Args:
            message_type: Message type to handle
            strategy: Function that takes FailedMessage and returns True if should retry
        """
        self._retry_strategies[message_type] = strategy
        logger.info(f"Registered retry strategy for message type: {message_type.value}")
    
    def _parse_failed_message(self, message_data: Any, message_type: MessageType) -> Optional[FailedMessage]:
        """Parse failed message data.
        
        Args:
            message_data: Raw message data
            message_type: Message type
            
        Returns:
            FailedMessage instance or None if parsing fails
        """
        try:
            # Extract failure metadata (added by RabbitMQ or our system)
            failure_info = message_data.get('failure_info', {})
            
            return FailedMessage(
                original_queue=failure_info.get('original_queue', 'unknown'),
                message_type=message_type,
                message_data=message_data.get('original_data', message_data),
                failure_reason=failure_info.get('reason', 'unknown'),
                failure_count=failure_info.get('failure_count', 1),
                first_failed_at=datetime.fromisoformat(
                    failure_info.get('first_failed_at', datetime.utcnow().isoformat())
                ),
                last_failed_at=datetime.fromisoformat(
                    failure_info.get('last_failed_at', datetime.utcnow().isoformat())
                ),
                original_routing_key=failure_info.get('original_routing_key', ''),
                original_properties=failure_info.get('original_properties', {})
            )
            
        except Exception as e:
            logger.error(f"Error parsing failed message: {e}")
            return None
    
    def _should_retry_message(self, failed_message: FailedMessage) -> bool:
        """Determine if a failed message should be retried.
        
        Args:
            failed_message: Failed message information
            
        Returns:
            True if message should be retried, False otherwise
        """
        # Check if we have a custom retry strategy
        strategy = self._retry_strategies.get(failed_message.message_type)
        if strategy:
            return strategy(failed_message)
        
        # Default retry logic
        if failed_message.failure_count >= self._max_retry_attempts:
            logger.info(f"Message exceeded max retry attempts ({self._max_retry_attempts})")
            return False
        
        # Check if enough time has passed since last failure
        now = datetime.utcnow()
        retry_delay_index = min(failed_message.failure_count - 1, len(self._retry_delay_minutes) - 1)
        retry_delay = timedelta(minutes=self._retry_delay_minutes[retry_delay_index])
        
        if now - failed_message.last_failed_at < retry_delay:
            logger.info(f"Not enough time passed for retry (need {retry_delay})")
            return False
        
        # Check message age - don't retry very old messages
        max_age = timedelta(hours=24)
        if now - failed_message.first_failed_at > max_age:
            logger.info("Message too old for retry")
            return False
        
        return True
    
    def _retry_message(self, failed_message: FailedMessage) -> bool:
        """Retry a failed message by republishing it.
        
        Args:
            failed_message: Failed message to retry
            
        Returns:
            True if retry successful, False otherwise
        """
        try:
            # Update failure metadata
            updated_data = failed_message.message_data.copy()
            if isinstance(updated_data, dict):
                updated_data['failure_info'] = {
                    'original_queue': failed_message.original_queue,
                    'reason': failed_message.failure_reason,
                    'failure_count': failed_message.failure_count + 1,
                    'first_failed_at': failed_message.first_failed_at.isoformat(),
                    'last_failed_at': datetime.utcnow().isoformat(),
                    'original_routing_key': failed_message.original_routing_key,
                    'original_properties': failed_message.original_properties,
                    'retry_attempt': failed_message.failure_count + 1
                }
            
            # Republish message to original routing key
            routing_key = failed_message.original_routing_key or self._get_default_routing_key(failed_message.message_type)
            
            success = self.publisher.publish_message(
                message=updated_data,
                message_type=failed_message.message_type,
                routing_key=routing_key,
                priority=1  # Lower priority for retries
            )
            
            if success:
                logger.info(f"Successfully retried message (attempt {failed_message.failure_count + 1})")
            else:
                logger.error("Failed to republish message for retry")
            
            return success
            
        except Exception as e:
            logger.error(f"Error retrying message: {e}")
            return False
    
    def _handle_permanently_failed_message(self, failed_message: FailedMessage) -> bool:
        """Handle a message that has permanently failed.
        
        Args:
            failed_message: Permanently failed message
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            # Log permanent failure
            logger.error(
                f"Message permanently failed after {failed_message.failure_count} attempts. "
                f"Type: {failed_message.message_type.value}, "
                f"Reason: {failed_message.failure_reason}, "
                f"First failed: {failed_message.first_failed_at}"
            )
            
            # Store in permanent failure log/database
            self._store_permanent_failure(failed_message)
            
            # Send alert for permanent failure
            self._send_permanent_failure_alert(failed_message)
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling permanently failed message: {e}")
            return False
    
    def _store_permanent_failure(self, failed_message: FailedMessage) -> None:
        """Store permanently failed message for analysis.
        
        Args:
            failed_message: Failed message to store
        """
        try:
            # This would typically store in a database or file
            # For now, we'll log the details
            failure_record = {
                'timestamp': datetime.utcnow().isoformat(),
                'message_type': failed_message.message_type.value,
                'original_queue': failed_message.original_queue,
                'failure_reason': failed_message.failure_reason,
                'failure_count': failed_message.failure_count,
                'first_failed_at': failed_message.first_failed_at.isoformat(),
                'last_failed_at': failed_message.last_failed_at.isoformat(),
                'message_data': str(failed_message.message_data)[:1000]  # Truncate for logging
            }
            
            logger.error(f"PERMANENT_FAILURE: {json.dumps(failure_record, indent=2)}")
            
        except Exception as e:
            logger.error(f"Error storing permanent failure: {e}")
    
    def _send_permanent_failure_alert(self, failed_message: FailedMessage) -> None:
        """Send alert for permanent message failure.
        
        Args:
            failed_message: Failed message to alert about
        """
        try:
            # Create alert message
            alert = {
                'alert_type': 'permanent_message_failure',
                'message_type': failed_message.message_type.value,
                'failure_count': failed_message.failure_count,
                'failure_reason': failed_message.failure_reason,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Publish alert (if notification system is available)
            self.publisher.publish_system_event(alert, priority=8)
            
        except Exception as e:
            logger.error(f"Error sending permanent failure alert: {e}")
    
    def _get_default_routing_key(self, message_type: MessageType) -> str:
        """Get default routing key for a message type.
        
        Args:
            message_type: Message type
            
        Returns:
            Default routing key
        """
        routing_key_map = {
            MessageType.BUG_REPORT: "bug_triage.new_bugs",
            MessageType.CATEGORIZED_BUG: "bug_triage.triaged_bugs",
            MessageType.ASSIGNMENT: "bug_triage.assignments",
            MessageType.NOTIFICATION: "bug_triage.notifications",
            MessageType.DEVELOPER_STATUS_UPDATE: "bug_triage.developer_status",
            MessageType.SYSTEM_EVENT: "bug_triage.system_events"
        }
        
        return routing_key_map.get(message_type, "bug_triage.unknown")
    
    def get_dead_letter_queue_stats(self) -> Dict[str, Any]:
        """Get statistics for all dead letter queues.
        
        Returns:
            Dictionary with dead letter queue statistics
        """
        stats = {}
        
        try:
            with self.connection.channel_context() as channel:
                for queue_key, queue_name in self.config.queue_names.items():
                    dlq_name = f"{queue_name}.dlq"
                    
                    try:
                        method = channel.queue_declare(queue=dlq_name, passive=True)
                        stats[queue_key] = {
                            'queue_name': dlq_name,
                            'message_count': method.method.message_count,
                            'consumer_count': method.method.consumer_count
                        }
                    except Exception as e:
                        logger.warning(f"Could not get stats for DLQ {dlq_name}: {e}")
                        stats[queue_key] = {'error': str(e)}
                        
        except Exception as e:
            logger.error(f"Error getting DLQ stats: {e}")
            stats['error'] = str(e)
        
        return stats
    
    def purge_dead_letter_queue(self, queue_key: str) -> bool:
        """Purge a specific dead letter queue.
        
        Args:
            queue_key: Key identifying the queue
            
        Returns:
            True if purged successfully, False otherwise
        """
        try:
            queue_name = self.config.queue_names.get(queue_key)
            if not queue_name:
                logger.error(f"Unknown queue key: {queue_key}")
                return False
            
            dlq_name = f"{queue_name}.dlq"
            
            with self.connection.channel_context() as channel:
                method = channel.queue_purge(queue=dlq_name)
                logger.info(f"Purged {method.method.message_count} messages from DLQ {dlq_name}")
                return True
                
        except Exception as e:
            logger.error(f"Error purging DLQ for {queue_key}: {e}")
            return False


class DeadLetterConsumer(MessageConsumer):
    """Specialized consumer for dead letter queues."""
    
    def __init__(self, connection: MessageQueueConnection, queue_key: str, publisher: MessagePublisher):
        """Initialize dead letter consumer.
        
        Args:
            connection: Message queue connection
            queue_key: Key identifying the main queue
            publisher: Message publisher for retries
        """
        queue_name = connection.config.queue_names.get(queue_key)
        if not queue_name:
            raise ValueError(f"Unknown queue key: {queue_key}")
        
        dlq_name = f"{queue_name}.dlq"
        super().__init__(connection, dlq_name)
        
        # Register dead letter handler
        self.dead_letter_handler = DeadLetterHandler(connection, publisher)
        self.register_handler(self.dead_letter_handler)
    
    def register_retry_strategy(self, message_type: MessageType, strategy: Callable[[FailedMessage], bool]) -> None:
        """Register a custom retry strategy.
        
        Args:
            message_type: Message type to handle
            strategy: Retry strategy function
        """
        self.dead_letter_handler.register_retry_strategy(message_type, strategy)