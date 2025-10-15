"""Message serialization and deserialization utilities."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Type, TypeVar
from dataclasses import asdict, is_dataclass
from enum import Enum

from ..models.common import BugReport, CategorizedBug, Assignment, AssignmentFeedback


logger = logging.getLogger(__name__)

T = TypeVar('T')


class MessageType(Enum):
    """Supported message types."""
    BUG_REPORT = "bug_report"
    CATEGORIZED_BUG = "categorized_bug"
    ASSIGNMENT = "assignment"
    ASSIGNMENT_FEEDBACK = "assignment_feedback"
    DEVELOPER_STATUS_UPDATE = "developer_status_update"
    NOTIFICATION = "notification"
    SYSTEM_EVENT = "system_event"


class MessageSerializer:
    """Handles serialization of messages for queue transmission."""
    
    @staticmethod
    def serialize(message: Any, message_type: MessageType) -> bytes:
        """Serialize a message object to bytes.
        
        Args:
            message: The message object to serialize
            message_type: Type of the message
            
        Returns:
            Serialized message as bytes
            
        Raises:
            ValueError: If message cannot be serialized
        """
        try:
            # Create message envelope
            envelope = {
                'type': message_type.value,
                'timestamp': datetime.utcnow().isoformat(),
                'data': MessageSerializer._serialize_data(message)
            }
            
            # Convert to JSON and encode
            json_str = json.dumps(envelope, default=MessageSerializer._json_serializer)
            return json_str.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to serialize message of type {message_type}: {e}")
            raise ValueError(f"Serialization failed: {e}")
    
    @staticmethod
    def _serialize_data(obj: Any) -> Dict[str, Any]:
        """Convert object to serializable dictionary.
        
        Args:
            obj: Object to serialize
            
        Returns:
            Dictionary representation of object
        """
        if is_dataclass(obj):
            return asdict(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        elif isinstance(obj, dict):
            return obj
        else:
            # For primitive types, wrap in a data field
            return {'value': obj}
    
    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Custom JSON serializer for special types.
        
        Args:
            obj: Object to serialize
            
        Returns:
            JSON-serializable representation
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Enum):
            return obj.value
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return str(obj)


class MessageDeserializer:
    """Handles deserialization of messages from queue transmission."""
    
    # Mapping of message types to their corresponding classes
    TYPE_MAPPING = {
        MessageType.BUG_REPORT: BugReport,
        MessageType.CATEGORIZED_BUG: CategorizedBug,
        MessageType.ASSIGNMENT: Assignment,
        MessageType.ASSIGNMENT_FEEDBACK: AssignmentFeedback,
    }
    
    @staticmethod
    def deserialize(data: bytes, expected_type: Optional[MessageType] = None) -> Dict[str, Any]:
        """Deserialize bytes to message object.
        
        Args:
            data: Serialized message bytes
            expected_type: Expected message type for validation
            
        Returns:
            Dictionary containing message metadata and deserialized data
            
        Raises:
            ValueError: If deserialization fails or type mismatch
        """
        try:
            # Decode and parse JSON
            json_str = data.decode('utf-8')
            envelope = json.loads(json_str)
            
            # Validate envelope structure
            if not all(key in envelope for key in ['type', 'timestamp', 'data']):
                raise ValueError("Invalid message envelope structure")
            
            # Parse message type
            try:
                message_type = MessageType(envelope['type'])
            except ValueError:
                raise ValueError(f"Unknown message type: {envelope['type']}")
            
            # Validate expected type if provided
            if expected_type and message_type != expected_type:
                raise ValueError(f"Expected {expected_type.value}, got {message_type.value}")
            
            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(envelope['timestamp'])
            except ValueError:
                logger.warning("Invalid timestamp format, using current time")
                timestamp = datetime.utcnow()
            
            # Deserialize data
            deserialized_data = MessageDeserializer._deserialize_data(
                envelope['data'], 
                message_type
            )
            
            return {
                'type': message_type,
                'timestamp': timestamp,
                'data': deserialized_data,
                'raw_envelope': envelope
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Invalid JSON format: {e}")
        except Exception as e:
            logger.error(f"Failed to deserialize message: {e}")
            raise ValueError(f"Deserialization failed: {e}")
    
    @staticmethod
    def _deserialize_data(data: Dict[str, Any], message_type: MessageType) -> Any:
        """Convert dictionary back to appropriate object type.
        
        Args:
            data: Dictionary data to deserialize
            message_type: Type of message for proper deserialization
            
        Returns:
            Deserialized object
        """
        # Get target class for this message type
        target_class = MessageDeserializer.TYPE_MAPPING.get(message_type)
        
        if target_class:
            try:
                # Handle datetime fields
                data = MessageDeserializer._convert_datetime_fields(data)
                
                # Create instance of target class
                if is_dataclass(target_class):
                    return target_class(**data)
                else:
                    # For non-dataclass types, try to create instance
                    return target_class(**data)
                    
            except Exception as e:
                logger.warning(f"Failed to create {target_class.__name__} instance: {e}")
                # Fall back to dictionary
                return data
        
        # For unknown types or fallback, return as dictionary
        return data
    
    @staticmethod
    def _convert_datetime_fields(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ISO datetime strings back to datetime objects.
        
        Args:
            data: Dictionary potentially containing datetime strings
            
        Returns:
            Dictionary with datetime objects
        """
        converted = data.copy()
        
        # Common datetime field names
        datetime_fields = [
            'created_at', 'updated_at', 'assigned_at', 'timestamp',
            'last_updated', 'last_activity', 'resolved_at'
        ]
        
        for field in datetime_fields:
            if field in converted and isinstance(converted[field], str):
                try:
                    converted[field] = datetime.fromisoformat(converted[field])
                except ValueError:
                    logger.warning(f"Could not parse datetime field {field}: {converted[field]}")
        
        return converted
    
    @staticmethod
    def extract_message_type(data: bytes) -> Optional[MessageType]:
        """Extract message type without full deserialization.
        
        Args:
            data: Serialized message bytes
            
        Returns:
            Message type if extractable, None otherwise
        """
        try:
            json_str = data.decode('utf-8')
            envelope = json.loads(json_str)
            
            if 'type' in envelope:
                return MessageType(envelope['type'])
                
        except Exception as e:
            logger.warning(f"Could not extract message type: {e}")
        
        return None


class MessageValidator:
    """Validates message content and structure."""
    
    @staticmethod
    def validate_message_envelope(envelope: Dict[str, Any]) -> bool:
        """Validate message envelope structure.
        
        Args:
            envelope: Message envelope to validate
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['type', 'timestamp', 'data']
        
        # Check required fields
        if not all(field in envelope for field in required_fields):
            return False
        
        # Validate message type
        try:
            MessageType(envelope['type'])
        except ValueError:
            return False
        
        # Validate timestamp format
        try:
            datetime.fromisoformat(envelope['timestamp'])
        except ValueError:
            return False
        
        # Validate data is a dictionary
        if not isinstance(envelope['data'], dict):
            return False
        
        return True
    
    @staticmethod
    def validate_message_data(data: Any, message_type: MessageType) -> bool:
        """Validate message data content.
        
        Args:
            data: Message data to validate
            message_type: Expected message type
            
        Returns:
            True if valid, False otherwise
        """
        try:
            target_class = MessageDeserializer.TYPE_MAPPING.get(message_type)
            
            if target_class and is_dataclass(target_class):
                # Try to create instance to validate
                if isinstance(data, dict):
                    target_class(**data)
                    return True
            
            # For other types, basic validation
            return data is not None
            
        except Exception:
            return False