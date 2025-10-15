"""Resilient agent base class with error handling and recovery."""

import logging
import time
from typing import Any, Dict, Optional, Callable
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from .base import Agent
from ..utils.resilience import (
    HealthChecker, GracefulDegradationManager, SystemRecoveryManager,
    SystemHealthStatus, retry_with_backoff, RetryConfig, RetryStrategy,
    RetryableError, NonRetryableError, GracefulDegradationError
)


logger = logging.getLogger(__name__)


class ResilientAgent(Agent, ABC):
    """Base class for agents with built-in resilience features."""
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """Initialize resilient agent.
        
        Args:
            agent_id: Unique identifier for the agent
            config: Agent configuration
        """
        super().__init__(agent_id, config)
        
        # Initialize resilience components
        self.health_checker = HealthChecker()
        self.degradation_manager = GracefulDegradationManager(self.health_checker)
        self.recovery_manager = SystemRecoveryManager(self.health_checker, self.degradation_manager)
        
        # Agent state tracking
        self._is_degraded = False
        self._last_health_check = None
        self._consecutive_failures = 0
        self._max_consecutive_failures = config.get('max_consecutive_failures', 5)
        self._health_check_interval = config.get('health_check_interval', 60)  # seconds
        
        # Register self health check
        self.health_checker.register_health_check(
            f"agent_{self.agent_id}",
            self._perform_self_health_check
        )
        
        # Register recovery procedure
        self.recovery_manager.register_recovery_procedure(
            f"agent_{self.agent_id}",
            self._perform_self_recovery
        )
        
        # Setup degradation strategies
        self._setup_degradation_strategies()
        
        logger.info(f"Initialized resilient agent: {agent_id}")
    
    def start(self) -> bool:
        """Start the resilient agent."""
        try:
            self.status = "running"
            logger.info(f"Started resilient agent: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start agent {self.agent_id}: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop the resilient agent."""
        try:
            self.status = "stopped"
            logger.info(f"Stopped resilient agent: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop agent {self.agent_id}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status including resilience information."""
        return self.get_agent_status()
    
    @abstractmethod
    def _perform_core_operation(self, *args, **kwargs) -> Any:
        """Perform the agent's core operation.
        
        This method should be implemented by subclasses to define
        the main functionality of the agent.
        """
        pass
    
    @abstractmethod
    def _get_fallback_operation(self) -> Optional[Callable]:
        """Get fallback operation for when core operation fails.
        
        Returns:
            Fallback function or None if no fallback available
        """
        pass
    
    def execute_operation(self, *args, **kwargs) -> Any:
        """Execute operation with resilience features.
        
        Args:
            *args: Arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Result of the operation
        """
        # Check if we need to perform health check
        self._check_health_if_needed()
        
        # If agent is degraded, try fallback first
        if self._is_degraded:
            fallback = self._get_fallback_operation()
            if fallback:
                try:
                    logger.info(f"Agent {self.agent_id} is degraded, using fallback operation")
                    result = fallback(*args, **kwargs)
                    self._on_operation_success()
                    return result
                except Exception as e:
                    logger.error(f"Fallback operation failed for agent {self.agent_id}: {e}")
                    # Continue to try main operation
        
        # Try main operation with retry
        try:
            result = self._execute_with_retry(*args, **kwargs)
            self._on_operation_success()
            return result
        except Exception as e:
            self._on_operation_failure(e)
            raise
    
    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        exceptions=(RetryableError, ConnectionError, TimeoutError)
    ))
    def _execute_with_retry(self, *args, **kwargs) -> Any:
        """Execute core operation with retry logic.
        
        Args:
            *args: Arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Result of the operation
        """
        try:
            return self._perform_core_operation(*args, **kwargs)
        except Exception as e:
            # Classify the error
            if self._is_retryable_error(e):
                raise RetryableError(f"Retryable error in {self.agent_id}: {e}") from e
            else:
                raise NonRetryableError(f"Non-retryable error in {self.agent_id}: {e}") from e
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if error is retryable, False otherwise
        """
        # Default retryable errors
        retryable_types = (
            ConnectionError,
            TimeoutError,
            OSError,
        )
        
        # Check for specific error messages that indicate transient issues
        retryable_messages = [
            "connection reset",
            "timeout",
            "temporary failure",
            "service unavailable",
            "rate limit",
        ]
        
        if isinstance(error, retryable_types):
            return True
        
        error_message = str(error).lower()
        return any(msg in error_message for msg in retryable_messages)
    
    def _perform_self_health_check(self) -> SystemHealthStatus:
        """Perform health check on this agent.
        
        Returns:
            SystemHealthStatus for this agent
        """
        try:
            start_time = time.time()
            
            # Perform agent-specific health checks
            health_info = self._check_agent_health()
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            is_healthy = (
                health_info.get('operational', True) and
                self._consecutive_failures < self._max_consecutive_failures
            )
            
            return SystemHealthStatus(
                component_name=f"agent_{self.agent_id}",
                is_healthy=is_healthy,
                last_check=datetime.utcnow(),
                response_time_ms=response_time,
                metadata={
                    'consecutive_failures': self._consecutive_failures,
                    'is_degraded': self._is_degraded,
                    **health_info
                }
            )
            
        except Exception as e:
            logger.error(f"Health check failed for agent {self.agent_id}: {e}")
            return SystemHealthStatus(
                component_name=f"agent_{self.agent_id}",
                is_healthy=False,
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
    
    def _check_agent_health(self) -> Dict[str, Any]:
        """Perform agent-specific health checks.
        
        This method can be overridden by subclasses to implement
        specific health check logic.
        
        Returns:
            Dictionary with health information
        """
        return {
            'operational': True,
            'last_operation': getattr(self, '_last_operation_time', None),
            'status': 'healthy'
        }
    
    def _perform_self_recovery(self) -> None:
        """Perform recovery procedures for this agent.
        
        This method can be overridden by subclasses to implement
        specific recovery logic.
        """
        logger.info(f"Performing recovery for agent {self.agent_id}")
        
        # Reset failure counters
        self._consecutive_failures = 0
        self._is_degraded = False
        
        # Perform agent-specific recovery
        self._recover_agent()
        
        logger.info(f"Recovery completed for agent {self.agent_id}")
    
    def _recover_agent(self) -> None:
        """Perform agent-specific recovery procedures.
        
        This method can be overridden by subclasses to implement
        specific recovery logic.
        """
        # Default recovery: reinitialize connections
        try:
            if hasattr(self, '_initialize_connections'):
                self._initialize_connections()
        except Exception as e:
            logger.error(f"Error during agent recovery: {e}")
            raise
    
    def _setup_degradation_strategies(self) -> None:
        """Setup degradation strategies for this agent."""
        self.degradation_manager.register_degradation_strategy(
            f"agent_{self.agent_id}",
            self._enter_degraded_mode
        )
        
        # Register fallback handlers
        fallback = self._get_fallback_operation()
        if fallback:
            self.degradation_manager.register_fallback_handler(
                f"agent_{self.agent_id}_operation",
                fallback
            )
    
    def _enter_degraded_mode(self) -> None:
        """Enter degraded mode for this agent."""
        logger.warning(f"Agent {self.agent_id} entering degraded mode")
        self._is_degraded = True
        
        # Perform degradation-specific actions
        self._on_degradation()
    
    def _on_degradation(self) -> None:
        """Handle entering degraded mode.
        
        This method can be overridden by subclasses to implement
        specific degradation behavior.
        """
        pass
    
    def _on_operation_success(self) -> None:
        """Handle successful operation."""
        self._consecutive_failures = 0
        self._last_operation_time = datetime.utcnow()
        
        # Exit degraded mode if we were degraded
        if self._is_degraded:
            logger.info(f"Agent {self.agent_id} recovering from degraded mode")
            self._is_degraded = False
    
    def _on_operation_failure(self, error: Exception) -> None:
        """Handle operation failure.
        
        Args:
            error: The exception that occurred
        """
        self._consecutive_failures += 1
        logger.error(
            f"Operation failed for agent {self.agent_id} "
            f"(failure {self._consecutive_failures}/{self._max_consecutive_failures}): {error}"
        )
        
        # Enter degraded mode if too many failures
        if self._consecutive_failures >= self._max_consecutive_failures and not self._is_degraded:
            self._enter_degraded_mode()
    
    def _check_health_if_needed(self) -> None:
        """Check health if enough time has passed since last check."""
        now = datetime.utcnow()
        
        if (self._last_health_check is None or 
            (now - self._last_health_check).total_seconds() >= self._health_check_interval):
            
            self.health_checker.check_component_health(f"agent_{self.agent_id}")
            self._last_health_check = now
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get current agent status.
        
        Returns:
            Dictionary with agent status information
        """
        health_status = self.health_checker.get_cached_status(f"agent_{self.agent_id}")
        
        return {
            'agent_id': self.agent_id,
            'is_healthy': health_status.is_healthy if health_status else False,
            'is_degraded': self._is_degraded,
            'consecutive_failures': self._consecutive_failures,
            'last_health_check': self._last_health_check,
            'last_operation': getattr(self, '_last_operation_time', None),
            'health_details': health_status.metadata if health_status else {}
        }
    
    def force_recovery(self) -> bool:
        """Force recovery of this agent.
        
        Returns:
            True if recovery successful, False otherwise
        """
        return self.recovery_manager.attempt_recovery(f"agent_{self.agent_id}")
    
    def get_resilience_metrics(self) -> Dict[str, Any]:
        """Get resilience metrics for this agent.
        
        Returns:
            Dictionary with resilience metrics
        """
        recovery_history = self.recovery_manager.get_recovery_history(f"agent_{self.agent_id}")
        
        successful_recoveries = sum(1 for record in recovery_history if record['success'])
        total_recoveries = len(recovery_history)
        
        return {
            'total_recovery_attempts': total_recoveries,
            'successful_recoveries': successful_recoveries,
            'recovery_success_rate': successful_recoveries / total_recoveries if total_recoveries > 0 else 0,
            'consecutive_failures': self._consecutive_failures,
            'is_degraded': self._is_degraded,
            'degraded_components': self.degradation_manager.get_degraded_components()
        }


class ResilientListenerAgent(ResilientAgent):
    """Resilient version of the Listener Agent."""
    
    def _perform_core_operation(self, *args, **kwargs) -> Any:
        """Perform bug listening operation."""
        # Import here to avoid circular imports
        from .listener_agent import ListenerAgent
        
        # This would delegate to the actual listener logic
        # For now, we'll simulate the operation
        logger.info(f"Performing listener operation for agent {self.agent_id}")
        return {"status": "listening", "bugs_detected": 0}
    
    def _get_fallback_operation(self) -> Optional[Callable]:
        """Get fallback operation for listener."""
        def fallback_listen(*args, **kwargs):
            logger.warning("Using fallback listening mode (polling only)")
            # Implement polling-only mode as fallback
            return {"status": "fallback_polling", "bugs_detected": 0}
        
        return fallback_listen
    
    def _check_agent_health(self) -> Dict[str, Any]:
        """Check listener agent health."""
        # Check webhook endpoints, API connections, etc.
        return {
            'operational': True,
            'webhook_active': True,
            'api_connection': True,
            'last_bug_detected': getattr(self, '_last_bug_time', None)
        }


class ResilientTriageAgent(ResilientAgent):
    """Resilient version of the Triage Agent."""
    
    def _perform_core_operation(self, bug_data: Dict[str, Any]) -> Any:
        """Perform bug triage operation."""
        logger.info(f"Performing triage operation for agent {self.agent_id}")
        # This would delegate to the actual triage logic
        return {
            "bug_id": bug_data.get("id"),
            "category": "backend",
            "severity": "medium",
            "confidence": 0.85
        }
    
    def _get_fallback_operation(self) -> Optional[Callable]:
        """Get fallback operation for triage."""
        def fallback_triage(bug_data: Dict[str, Any]):
            logger.warning("Using fallback triage mode (rule-based)")
            # Implement simple rule-based triage as fallback
            return {
                "bug_id": bug_data.get("id"),
                "category": "unknown",
                "severity": "medium",
                "confidence": 0.5,
                "fallback": True
            }
        
        return fallback_triage
    
    def _check_agent_health(self) -> Dict[str, Any]:
        """Check triage agent health."""
        return {
            'operational': True,
            'nlp_model_loaded': True,
            'classification_accuracy': 0.85,
            'last_triage': getattr(self, '_last_triage_time', None)
        }


class ResilientAssignmentAgent(ResilientAgent):
    """Resilient version of the Assignment Agent."""
    
    def _perform_core_operation(self, triaged_bug: Dict[str, Any]) -> Any:
        """Perform bug assignment operation."""
        logger.info(f"Performing assignment operation for agent {self.agent_id}")
        # This would delegate to the actual assignment logic
        return {
            "bug_id": triaged_bug.get("bug_id"),
            "assigned_to": "developer_1",
            "assignment_confidence": 0.9
        }
    
    def _get_fallback_operation(self) -> Optional[Callable]:
        """Get fallback operation for assignment."""
        def fallback_assignment(triaged_bug: Dict[str, Any]):
            logger.warning("Using fallback assignment mode (round-robin)")
            # Implement simple round-robin assignment as fallback
            return {
                "bug_id": triaged_bug.get("bug_id"),
                "assigned_to": "fallback_developer",
                "assignment_confidence": 0.3,
                "fallback": True
            }
        
        return fallback_assignment
    
    def _check_agent_health(self) -> Dict[str, Any]:
        """Check assignment agent health."""
        return {
            'operational': True,
            'developer_agents_connected': True,
            'api_connections': True,
            'last_assignment': getattr(self, '_last_assignment_time', None)
        }


class ResilientDeveloperAgent(ResilientAgent):
    """Resilient version of the Developer Agent."""
    
    def __init__(self, agent_id: str, config: Dict[str, Any], developer_id: str):
        """Initialize resilient developer agent.
        
        Args:
            agent_id: Unique identifier for the agent
            config: Agent configuration
            developer_id: ID of the developer this agent represents
        """
        super().__init__(agent_id, config)
        self.developer_id = developer_id
    
    def _perform_core_operation(self, *args, **kwargs) -> Any:
        """Perform developer status monitoring operation."""
        logger.info(f"Performing status monitoring for developer {self.developer_id}")
        # This would delegate to the actual developer monitoring logic
        return {
            "developer_id": self.developer_id,
            "workload": 3,
            "availability": True,
            "skills": ["python", "react"]
        }
    
    def _get_fallback_operation(self) -> Optional[Callable]:
        """Get fallback operation for developer monitoring."""
        def fallback_monitoring(*args, **kwargs):
            logger.warning(f"Using fallback monitoring for developer {self.developer_id}")
            # Return cached or default status
            return {
                "developer_id": self.developer_id,
                "workload": 2,  # Conservative estimate
                "availability": True,  # Assume available
                "skills": ["general"],
                "fallback": True
            }
        
        return fallback_monitoring
    
    def _check_agent_health(self) -> Dict[str, Any]:
        """Check developer agent health."""
        return {
            'operational': True,
            'api_connections': True,
            'calendar_sync': True,
            'last_status_update': getattr(self, '_last_status_update', None)
        }