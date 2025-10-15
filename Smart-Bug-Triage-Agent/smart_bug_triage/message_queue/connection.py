"""RabbitMQ connection and channel management."""

import logging
import threading
import time
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from ..config.settings import MessageQueueConfig


logger = logging.getLogger(__name__)


class MessageQueueConnection:
    """Manages RabbitMQ connection and channel lifecycle."""
    
    def __init__(self, config: MessageQueueConfig):
        """Initialize connection manager with configuration.
        
        Args:
            config: Message queue configuration
        """
        self.config = config
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[BlockingChannel] = None
        self._lock = threading.Lock()
        self._is_connected = False
        
    def connect(self) -> bool:
        """Establish connection to RabbitMQ server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._lock:
                if self._is_connected:
                    return True
                
                # Create connection parameters
                credentials = pika.PlainCredentials(
                    self.config.username,
                    self.config.password
                )
                
                parameters = pika.ConnectionParameters(
                    host=self.config.host,
                    port=self.config.port,
                    virtual_host=self.config.virtual_host,
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
                
                # Establish connection
                self._connection = pika.BlockingConnection(parameters)
                self._channel = self._connection.channel()
                
                # Set up exchange and queues
                self._setup_infrastructure()
                
                self._is_connected = True
                logger.info(f"Connected to RabbitMQ at {self.config.host}:{self.config.port}")
                return True
                
        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to RabbitMQ: {e}")
            return False
    
    def disconnect(self) -> None:
        """Close connection to RabbitMQ server."""
        try:
            with self._lock:
                if self._connection and not self._connection.is_closed:
                    self._connection.close()
                
                self._connection = None
                self._channel = None
                self._is_connected = False
                logger.info("Disconnected from RabbitMQ")
                
        except Exception as e:
            logger.error(f"Error disconnecting from RabbitMQ: {e}")
    
    def is_connected(self) -> bool:
        """Check if connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        with self._lock:
            return (self._is_connected and 
                    self._connection and 
                    not self._connection.is_closed)
    
    def get_channel(self) -> Optional[BlockingChannel]:
        """Get the current channel.
        
        Returns:
            Channel if connected, None otherwise
        """
        if not self.is_connected():
            if not self.connect():
                return None
        
        return self._channel
    
    @contextmanager
    def channel_context(self):
        """Context manager for safe channel operations."""
        channel = self.get_channel()
        if not channel:
            raise AMQPConnectionError("Could not establish channel")
        
        try:
            yield channel
        except AMQPChannelError as e:
            logger.error(f"Channel error: {e}")
            # Try to reconnect
            self._is_connected = False
            raise
        except Exception as e:
            logger.error(f"Unexpected error in channel context: {e}")
            raise
    
    def _setup_infrastructure(self) -> None:
        """Set up exchange, queues, and bindings."""
        if not self._channel:
            raise AMQPConnectionError("No channel available")
        
        # Declare exchange
        self._channel.exchange_declare(
            exchange=self.config.exchange_name,
            exchange_type='topic',
            durable=True
        )
        
        # Declare queues with dead letter exchange
        dead_letter_exchange = f"{self.config.exchange_name}.dlx"
        
        # Declare dead letter exchange
        self._channel.exchange_declare(
            exchange=dead_letter_exchange,
            exchange_type='direct',
            durable=True
        )
        
        # Declare main queues
        for queue_key, queue_name in self.config.queue_names.items():
            # Main queue with dead letter configuration
            self._channel.queue_declare(
                queue=queue_name,
                durable=True,
                arguments={
                    'x-dead-letter-exchange': dead_letter_exchange,
                    'x-dead-letter-routing-key': f"{queue_name}.failed"
                }
            )
            
            # Dead letter queue
            dead_letter_queue = f"{queue_name}.dlq"
            self._channel.queue_declare(
                queue=dead_letter_queue,
                durable=True
            )
            
            # Bind dead letter queue
            self._channel.queue_bind(
                exchange=dead_letter_exchange,
                queue=dead_letter_queue,
                routing_key=f"{queue_name}.failed"
            )
            
            # Bind main queue to exchange
            routing_key = f"bug_triage.{queue_key}"
            self._channel.queue_bind(
                exchange=self.config.exchange_name,
                queue=queue_name,
                routing_key=routing_key
            )
        
        logger.info("Message queue infrastructure set up successfully")
    
    def reconnect_with_backoff(self, max_retries: int = 5, base_delay: float = 1.0) -> bool:
        """Reconnect with exponential backoff.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds
            
        Returns:
            True if reconnection successful, False otherwise
        """
        for attempt in range(max_retries):
            if self.connect():
                return True
            
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Reconnection attempt {attempt + 1} failed, retrying in {delay}s")
            time.sleep(delay)
        
        logger.error(f"Failed to reconnect after {max_retries} attempts")
        return False
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on connection.
        
        Returns:
            Dictionary with health status information
        """
        status = {
            'connected': False,
            'channel_open': False,
            'exchange_exists': False,
            'queues_exist': {},
            'timestamp': time.time()
        }
        
        try:
            status['connected'] = self.is_connected()
            
            if status['connected'] and self._channel:
                status['channel_open'] = self._channel.is_open
                
                # Check if exchange exists by declaring it (idempotent)
                try:
                    self._channel.exchange_declare(
                        exchange=self.config.exchange_name,
                        exchange_type='topic',
                        durable=True,
                        passive=True  # Only check existence
                    )
                    status['exchange_exists'] = True
                except Exception:
                    status['exchange_exists'] = False
                
                # Check queues
                for queue_key, queue_name in self.config.queue_names.items():
                    try:
                        method = self._channel.queue_declare(
                            queue=queue_name,
                            durable=True,
                            passive=True  # Only check existence
                        )
                        status['queues_exist'][queue_key] = {
                            'exists': True,
                            'message_count': method.method.message_count,
                            'consumer_count': method.method.consumer_count
                        }
                    except Exception:
                        status['queues_exist'][queue_key] = {'exists': False}
        
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            status['error'] = str(e)
        
        return status