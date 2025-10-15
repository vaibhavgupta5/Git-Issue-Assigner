"""Message consumer for receiving messages from queues."""

import logging
import threading
import time
from typing import Callable, Optional, Dict, Any, List
from datetime import datetime
from abc import ABC, abstractmethod

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from .connection import MessageQueueConnection
from .serialization import MessageDeserializer, MessageType, MessageValidator
from ..config.settings import MessageQueueConfig


logger = logging.getLogger(__name__)


class MessageHandler(ABC):
    """Abstract base class for message handlers."""
    
    @abstractmethod
    def handle_message(self, message_data: Any, message_type: MessageType, delivery_tag: str) -> bool:
        """Handle a received message.
        
        Args:
            message_data: Deserialized message data
            message_type: Type of the message
            delivery_tag: Delivery tag for acknowledgment
            
        Returns:
            True if message processed successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def get_supported_message_types(self) -> List[MessageType]:
        """Get list of message types this handler supports.
        
        Returns:
            List of supported message types
        """
        pass


class MessageConsumer:
    """Base class for consuming messages from RabbitMQ queues."""
    
    def __init__(self, connection: MessageQueueConnection, queue_name: str):
        """Initialize consumer with connection and queue.
        
        Args:
            connection: Message queue connection instance
            queue_name: Name of the queue to consume from
        """
        self.connection = connection
        self.queue_name = queue_name
        self.config = connection.config
        self._handlers: Dict[MessageType, MessageHandler] = {}
        self._is_consuming = False
        self._consumer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._consume_stats = {
            'total_consumed': 0,
            'successful_processed': 0,
            'failed_processed': 0,
            'last_consume_time': None
        }
    
    def register_handler(self, handler: MessageHandler) -> None:
        """Register a message handler for specific message types.
        
        Args:
            handler: Message handler instance
        """
        supported_types = handler.get_supported_message_types()
        for message_type in supported_types:
            self._handlers[message_type] = handler
            logger.info(f"Registered handler for message type: {message_type.value}")
    
    def start_consuming(self, prefetch_count: int = 10, auto_ack: bool = False) -> bool:
        """Start consuming messages from the queue.
        
        Args:
            prefetch_count: Number of messages to prefetch
            auto_ack: Whether to auto-acknowledge messages
            
        Returns:
            True if consuming started successfully, False otherwise
        """
        if self._is_consuming:
            logger.warning("Consumer is already running")
            return True
        
        try:
            # Start consumer in separate thread
            self._consumer_thread = threading.Thread(
                target=self._consume_loop,
                args=(prefetch_count, auto_ack),
                daemon=True
            )
            self._consumer_thread.start()
            
            self._is_consuming = True
            logger.info(f"Started consuming from queue: {self.queue_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start consuming: {e}")
            return False
    
    def stop_consuming(self, timeout: float = 10.0) -> bool:
        """Stop consuming messages.
        
        Args:
            timeout: Maximum time to wait for consumer to stop
            
        Returns:
            True if stopped successfully, False otherwise
        """
        if not self._is_consuming:
            return True
        
        try:
            # Signal stop
            self._stop_event.set()
            
            # Wait for consumer thread to finish
            if self._consumer_thread and self._consumer_thread.is_alive():
                self._consumer_thread.join(timeout=timeout)
                
                if self._consumer_thread.is_alive():
                    logger.warning("Consumer thread did not stop within timeout")
                    return False
            
            self._is_consuming = False
            self._stop_event.clear()
            logger.info(f"Stopped consuming from queue: {self.queue_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping consumer: {e}")
            return False
    
    def _consume_loop(self, prefetch_count: int, auto_ack: bool) -> None:
        """Main consuming loop running in separate thread.
        
        Args:
            prefetch_count: Number of messages to prefetch
            auto_ack: Whether to auto-acknowledge messages
        """
        while not self._stop_event.is_set():
            try:
                with self.connection.channel_context() as channel:
                    # Set QoS
                    channel.basic_qos(prefetch_count=prefetch_count)
                    
                    # Set up consumer
                    def callback(ch, method, properties, body):
                        self._handle_message(ch, method, properties, body, auto_ack)
                    
                    # Start consuming
                    consumer_tag = channel.basic_consume(
                        queue=self.queue_name,
                        on_message_callback=callback,
                        auto_ack=auto_ack
                    )
                    
                    logger.info(f"Started consuming with tag: {consumer_tag}")
                    
                    # Consume messages until stop signal
                    while not self._stop_event.is_set():
                        try:
                            # Process messages with timeout
                            self.connection._connection.process_data_events(time_limit=1.0)
                        except Exception as e:
                            logger.error(f"Error processing data events: {e}")
                            break
                    
                    # Cancel consumer
                    try:
                        channel.basic_cancel(consumer_tag)
                    except Exception as e:
                        logger.warning(f"Error canceling consumer: {e}")
                        
            except (AMQPConnectionError, AMQPChannelError) as e:
                logger.error(f"Connection error in consume loop: {e}")
                if not self._stop_event.is_set():
                    # Try to reconnect
                    time.sleep(5)
                    self.connection.reconnect_with_backoff()
                    
            except Exception as e:
                logger.error(f"Unexpected error in consume loop: {e}")
                if not self._stop_event.is_set():
                    time.sleep(5)
    
    def _handle_message(self, channel, method, properties, body: bytes, auto_ack: bool) -> None:
        """Handle a received message.
        
        Args:
            channel: Channel instance
            method: Method frame
            properties: Message properties
            body: Message body
            auto_ack: Whether auto-acknowledgment is enabled
        """
        delivery_tag = method.delivery_tag
        
        try:
            # Update statistics
            self._consume_stats['total_consumed'] += 1
            self._consume_stats['last_consume_time'] = datetime.utcnow()
            
            # Deserialize message
            message_info = MessageDeserializer.deserialize(body)
            message_type = message_info['type']
            message_data = message_info['data']
            
            # Validate message
            if not MessageValidator.validate_message_envelope(message_info['raw_envelope']):
                logger.error(f"Invalid message envelope for delivery tag {delivery_tag}")
                self._reject_message(channel, delivery_tag, requeue=False)
                return
            
            # Find appropriate handler
            handler = self._handlers.get(message_type)
            if not handler:
                logger.warning(f"No handler registered for message type: {message_type.value}")
                self._reject_message(channel, delivery_tag, requeue=False)
                return
            
            # Process message
            success = handler.handle_message(message_data, message_type, str(delivery_tag))
            
            if success:
                self._consume_stats['successful_processed'] += 1
                if not auto_ack:
                    channel.basic_ack(delivery_tag=delivery_tag)
                logger.debug(f"Successfully processed message {delivery_tag}")
            else:
                self._consume_stats['failed_processed'] += 1
                self._reject_message(channel, delivery_tag, requeue=True)
                logger.warning(f"Handler failed to process message {delivery_tag}")
                
        except Exception as e:
            logger.error(f"Error handling message {delivery_tag}: {e}")
            self._consume_stats['failed_processed'] += 1
            self._reject_message(channel, delivery_tag, requeue=False)
    
    def _reject_message(self, channel, delivery_tag: int, requeue: bool = False) -> None:
        """Reject a message.
        
        Args:
            channel: Channel instance
            delivery_tag: Message delivery tag
            requeue: Whether to requeue the message
        """
        try:
            channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
        except Exception as e:
            logger.error(f"Error rejecting message {delivery_tag}: {e}")
    
    def consume_single_message(self, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Consume a single message synchronously.
        
        Args:
            timeout: Maximum time to wait for a message
            
        Returns:
            Message information if received, None otherwise
        """
        try:
            with self.connection.channel_context() as channel:
                # Get a single message
                method, properties, body = channel.basic_get(
                    queue=self.queue_name,
                    auto_ack=False
                )
                
                if method is None:
                    return None  # No message available
                
                try:
                    # Deserialize message
                    message_info = MessageDeserializer.deserialize(body)
                    
                    # Add delivery information
                    message_info['delivery_tag'] = method.delivery_tag
                    message_info['redelivered'] = method.redelivered
                    
                    return message_info
                    
                except Exception as e:
                    logger.error(f"Error deserializing single message: {e}")
                    # Reject the message
                    channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return None
                    
        except Exception as e:
            logger.error(f"Error consuming single message: {e}")
            return None
    
    def acknowledge_message(self, delivery_tag: str) -> bool:
        """Acknowledge a message by delivery tag.
        
        Args:
            delivery_tag: Message delivery tag
            
        Returns:
            True if acknowledged successfully, False otherwise
        """
        try:
            with self.connection.channel_context() as channel:
                channel.basic_ack(delivery_tag=int(delivery_tag))
                return True
        except Exception as e:
            logger.error(f"Error acknowledging message {delivery_tag}: {e}")
            return False
    
    def reject_message(self, delivery_tag: str, requeue: bool = False) -> bool:
        """Reject a message by delivery tag.
        
        Args:
            delivery_tag: Message delivery tag
            requeue: Whether to requeue the message
            
        Returns:
            True if rejected successfully, False otherwise
        """
        try:
            with self.connection.channel_context() as channel:
                channel.basic_nack(delivery_tag=int(delivery_tag), requeue=requeue)
                return True
        except Exception as e:
            logger.error(f"Error rejecting message {delivery_tag}: {e}")
            return False
    
    def get_queue_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the queue.
        
        Returns:
            Dictionary with queue information or None if error
        """
        try:
            with self.connection.channel_context() as channel:
                method = channel.queue_declare(queue=self.queue_name, passive=True)
                return {
                    'queue_name': self.queue_name,
                    'message_count': method.method.message_count,
                    'consumer_count': method.method.consumer_count
                }
        except Exception as e:
            logger.error(f"Error getting queue info: {e}")
            return None
    
    def purge_queue(self) -> bool:
        """Purge all messages from the queue.
        
        Returns:
            True if purged successfully, False otherwise
        """
        try:
            with self.connection.channel_context() as channel:
                method = channel.queue_purge(queue=self.queue_name)
                logger.info(f"Purged {method.method.message_count} messages from queue {self.queue_name}")
                return True
        except Exception as e:
            logger.error(f"Error purging queue: {e}")
            return False
    
    def is_consuming(self) -> bool:
        """Check if consumer is currently running.
        
        Returns:
            True if consuming, False otherwise
        """
        return self._is_consuming
    
    def get_consume_stats(self) -> Dict[str, Any]:
        """Get consuming statistics.
        
        Returns:
            Dictionary with consuming statistics
        """
        stats = self._consume_stats.copy()
        
        # Calculate success rate
        total_processed = stats['successful_processed'] + stats['failed_processed']
        if total_processed > 0:
            stats['success_rate'] = stats['successful_processed'] / total_processed
        else:
            stats['success_rate'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset consuming statistics."""
        self._consume_stats = {
            'total_consumed': 0,
            'successful_processed': 0,
            'failed_processed': 0,
            'last_consume_time': None
        }