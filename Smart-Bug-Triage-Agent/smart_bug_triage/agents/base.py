"""Base Agent interface and common functionality."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging


class Agent(ABC):
    """Base class for all agents in the smart bug triage system."""
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.logger = logging.getLogger(f"{self.__class__.__name__}_{agent_id}")
        self.status = "initialized"
        self.last_heartbeat = datetime.now()
        
    @abstractmethod
    def start(self) -> bool:
        """Start the agent's main processing loop."""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop the agent gracefully."""
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status and health information."""
        pass
    
    def heartbeat(self) -> None:
        """Update the agent's heartbeat timestamp."""
        self.last_heartbeat = datetime.now()
        self.logger.debug(f"Heartbeat updated for agent {self.agent_id}")
    
    def is_healthy(self) -> bool:
        """Check if the agent is healthy based on recent heartbeat."""
        time_since_heartbeat = (datetime.now() - self.last_heartbeat).total_seconds()
        return time_since_heartbeat < 300  # 5 minutes threshold
    
    def log_error(self, message: str, exception: Optional[Exception] = None) -> None:
        """Log an error with optional exception details."""
        if exception:
            self.logger.error(f"{message}: {str(exception)}", exc_info=True)
        else:
            self.logger.error(message)
    
    def log_info(self, message: str) -> None:
        """Log an informational message."""
        self.logger.info(message)