"""Resilience utilities for error handling and system recovery."""

import logging
import time
import functools
import threading
from typing import Any, Callable, Dict, List, Optional, Type, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import random


logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategy types."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"
    FIBONACCI_BACKOFF = "fibonacci_backoff"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    jitter: bool = True
    backoff_multiplier: float = 2.0
    exceptions: tuple = (Exception,)


@dataclass
class SystemHealthStatus:
    """System health status information."""
    component_name: str
    is_healthy: bool
    last_check: datetime
    error_message: Optional[str] = None
    response_time_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RetryableError(Exception):
    """Exception that indicates an operation should be retried."""
    pass


class NonRetryableError(Exception):
    """Exception that indicates an operation should not be retried."""
    pass


class GracefulDegradationError(Exception):
    """Exception that indicates system should degrade gracefully."""
    pass


def retry_with_backoff(config: RetryConfig = None):
    """Decorator for retrying functions with configurable backoff strategy.
    
    Args:
        config: Retry configuration
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.exceptions as e:
                    last_exception = e
                    
                    # Don't retry on non-retryable errors
                    if isinstance(e, NonRetryableError):
                        logger.error(f"Non-retryable error in {func.__name__}: {e}")
                        raise e
                    
                    # Log retry attempt
                    if attempt < config.max_attempts - 1:
                        delay = _calculate_delay(attempt, config)
                        logger.warning(
                            f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {config.max_attempts} attempts failed for {func.__name__}")
            
            # All attempts failed
            raise last_exception
        
        return wrapper
    return decorator


def _calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for retry attempt.
    
    Args:
        attempt: Current attempt number (0-based)
        config: Retry configuration
        
    Returns:
        Delay in seconds
    """
    if config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
        delay = config.base_delay * (config.backoff_multiplier ** attempt)
    elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
        delay = config.base_delay * (attempt + 1)
    elif config.strategy == RetryStrategy.FIXED_DELAY:
        delay = config.base_delay
    elif config.strategy == RetryStrategy.FIBONACCI_BACKOFF:
        fib_sequence = [1, 1]
        for i in range(2, attempt + 2):
            fib_sequence.append(fib_sequence[i-1] + fib_sequence[i-2])
        delay = config.base_delay * fib_sequence[attempt + 1]
    else:
        delay = config.base_delay
    
    # Apply maximum delay limit
    delay = min(delay, config.max_delay)
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        jitter_amount = delay * 0.1 * random.random()
        delay += jitter_amount
    
    return delay


class HealthChecker:
    """Health checker for system components."""
    
    def __init__(self):
        """Initialize health checker."""
        self._health_checks: Dict[str, Callable[[], SystemHealthStatus]] = {}
        self._health_status: Dict[str, SystemHealthStatus] = {}
        self._lock = threading.Lock()
    
    def register_health_check(self, component_name: str, check_func: Callable[[], SystemHealthStatus]) -> None:
        """Register a health check function for a component.
        
        Args:
            component_name: Name of the component
            check_func: Function that returns SystemHealthStatus
        """
        with self._lock:
            self._health_checks[component_name] = check_func
            logger.info(f"Registered health check for component: {component_name}")
    
    def check_component_health(self, component_name: str) -> SystemHealthStatus:
        """Check health of a specific component.
        
        Args:
            component_name: Name of the component to check
            
        Returns:
            SystemHealthStatus for the component
        """
        check_func = self._health_checks.get(component_name)
        if not check_func:
            return SystemHealthStatus(
                component_name=component_name,
                is_healthy=False,
                last_check=datetime.utcnow(),
                error_message=f"No health check registered for {component_name}"
            )
        
        try:
            start_time = time.time()
            status = check_func()
            end_time = time.time()
            
            # Update response time
            status.response_time_ms = (end_time - start_time) * 1000
            status.last_check = datetime.utcnow()
            
            # Cache status
            with self._lock:
                self._health_status[component_name] = status
            
            return status
            
        except Exception as e:
            logger.error(f"Health check failed for {component_name}: {e}")
            status = SystemHealthStatus(
                component_name=component_name,
                is_healthy=False,
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
            
            with self._lock:
                self._health_status[component_name] = status
            
            return status
    
    def check_all_components(self) -> Dict[str, SystemHealthStatus]:
        """Check health of all registered components.
        
        Returns:
            Dictionary mapping component names to their health status
        """
        results = {}
        
        for component_name in self._health_checks.keys():
            results[component_name] = self.check_component_health(component_name)
        
        return results
    
    def get_cached_status(self, component_name: str) -> Optional[SystemHealthStatus]:
        """Get cached health status for a component.
        
        Args:
            component_name: Name of the component
            
        Returns:
            Cached SystemHealthStatus or None if not available
        """
        with self._lock:
            return self._health_status.get(component_name)
    
    def get_overall_health(self) -> bool:
        """Get overall system health status.
        
        Returns:
            True if all components are healthy, False otherwise
        """
        statuses = self.check_all_components()
        return all(status.is_healthy for status in statuses.values())


class GracefulDegradationManager:
    """Manages graceful degradation of system functionality."""
    
    def __init__(self, health_checker: HealthChecker):
        """Initialize graceful degradation manager.
        
        Args:
            health_checker: Health checker instance
        """
        self.health_checker = health_checker
        self._degradation_strategies: Dict[str, Callable] = {}
        self._fallback_handlers: Dict[str, Callable] = {}
        self._degraded_components: set = set()
        self._lock = threading.Lock()
    
    def register_degradation_strategy(self, component_name: str, strategy: Callable) -> None:
        """Register a degradation strategy for a component.
        
        Args:
            component_name: Name of the component
            strategy: Function to call when component fails
        """
        with self._lock:
            self._degradation_strategies[component_name] = strategy
            logger.info(f"Registered degradation strategy for: {component_name}")
    
    def register_fallback_handler(self, operation_name: str, handler: Callable) -> None:
        """Register a fallback handler for an operation.
        
        Args:
            operation_name: Name of the operation
            handler: Fallback function to use when primary operation fails
        """
        with self._lock:
            self._fallback_handlers[operation_name] = handler
            logger.info(f"Registered fallback handler for: {operation_name}")
    
    def execute_with_fallback(self, operation_name: str, primary_func: Callable, *args, **kwargs) -> Any:
        """Execute operation with fallback if primary fails.
        
        Args:
            operation_name: Name of the operation
            primary_func: Primary function to execute
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result from primary function or fallback
        """
        try:
            return primary_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Primary operation {operation_name} failed: {e}")
            
            # Try fallback
            fallback = self._fallback_handlers.get(operation_name)
            if fallback:
                try:
                    logger.info(f"Using fallback for operation: {operation_name}")
                    return fallback(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {operation_name}: {fallback_error}")
                    raise GracefulDegradationError(
                        f"Both primary and fallback failed for {operation_name}"
                    )
            else:
                logger.error(f"No fallback registered for operation: {operation_name}")
                raise e
    
    def check_and_degrade(self) -> None:
        """Check component health and apply degradation strategies."""
        health_statuses = self.health_checker.check_all_components()
        
        with self._lock:
            for component_name, status in health_statuses.items():
                if not status.is_healthy and component_name not in self._degraded_components:
                    # Component became unhealthy
                    self._apply_degradation(component_name)
                    self._degraded_components.add(component_name)
                elif status.is_healthy and component_name in self._degraded_components:
                    # Component recovered
                    self._recover_component(component_name)
                    self._degraded_components.discard(component_name)
    
    def _apply_degradation(self, component_name: str) -> None:
        """Apply degradation strategy for a component.
        
        Args:
            component_name: Name of the component to degrade
        """
        strategy = self._degradation_strategies.get(component_name)
        if strategy:
            try:
                logger.warning(f"Applying degradation strategy for: {component_name}")
                strategy()
            except Exception as e:
                logger.error(f"Error applying degradation strategy for {component_name}: {e}")
        else:
            logger.warning(f"No degradation strategy for component: {component_name}")
    
    def _recover_component(self, component_name: str) -> None:
        """Handle component recovery.
        
        Args:
            component_name: Name of the recovered component
        """
        logger.info(f"Component recovered: {component_name}")
        # Could implement recovery strategies here
    
    def get_degraded_components(self) -> List[str]:
        """Get list of currently degraded components.
        
        Returns:
            List of degraded component names
        """
        with self._lock:
            return list(self._degraded_components)
    
    def is_component_degraded(self, component_name: str) -> bool:
        """Check if a component is currently degraded.
        
        Args:
            component_name: Name of the component
            
        Returns:
            True if component is degraded, False otherwise
        """
        with self._lock:
            return component_name in self._degraded_components


class SystemRecoveryManager:
    """Manages system recovery procedures."""
    
    def __init__(self, health_checker: HealthChecker, degradation_manager: GracefulDegradationManager):
        """Initialize system recovery manager.
        
        Args:
            health_checker: Health checker instance
            degradation_manager: Graceful degradation manager
        """
        self.health_checker = health_checker
        self.degradation_manager = degradation_manager
        self._recovery_procedures: Dict[str, Callable] = {}
        self._recovery_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
    
    def register_recovery_procedure(self, component_name: str, procedure: Callable) -> None:
        """Register a recovery procedure for a component.
        
        Args:
            component_name: Name of the component
            procedure: Recovery function
        """
        with self._lock:
            self._recovery_procedures[component_name] = procedure
            logger.info(f"Registered recovery procedure for: {component_name}")
    
    def attempt_recovery(self, component_name: str) -> bool:
        """Attempt to recover a failed component.
        
        Args:
            component_name: Name of the component to recover
            
        Returns:
            True if recovery successful, False otherwise
        """
        procedure = self._recovery_procedures.get(component_name)
        if not procedure:
            logger.warning(f"No recovery procedure for component: {component_name}")
            return False
        
        recovery_start = datetime.utcnow()
        
        try:
            logger.info(f"Attempting recovery for component: {component_name}")
            procedure()
            
            # Verify recovery by checking health
            time.sleep(2)  # Give component time to stabilize
            status = self.health_checker.check_component_health(component_name)
            
            recovery_record = {
                'component_name': component_name,
                'recovery_time': recovery_start,
                'success': status.is_healthy,
                'duration_seconds': (datetime.utcnow() - recovery_start).total_seconds(),
                'error_message': status.error_message if not status.is_healthy else None
            }
            
            with self._lock:
                self._recovery_history.append(recovery_record)
            
            if status.is_healthy:
                logger.info(f"Successfully recovered component: {component_name}")
                return True
            else:
                logger.error(f"Recovery failed for component {component_name}: {status.error_message}")
                return False
                
        except Exception as e:
            logger.error(f"Error during recovery of {component_name}: {e}")
            
            recovery_record = {
                'component_name': component_name,
                'recovery_time': recovery_start,
                'success': False,
                'duration_seconds': (datetime.utcnow() - recovery_start).total_seconds(),
                'error_message': str(e)
            }
            
            with self._lock:
                self._recovery_history.append(recovery_record)
            
            return False
    
    def auto_recovery_check(self) -> None:
        """Perform automatic recovery check for all components."""
        health_statuses = self.health_checker.check_all_components()
        
        for component_name, status in health_statuses.items():
            if not status.is_healthy:
                # Check if we should attempt recovery
                if self._should_attempt_recovery(component_name):
                    self.attempt_recovery(component_name)
    
    def _should_attempt_recovery(self, component_name: str) -> bool:
        """Determine if recovery should be attempted for a component.
        
        Args:
            component_name: Name of the component
            
        Returns:
            True if recovery should be attempted, False otherwise
        """
        with self._lock:
            # Check recent recovery attempts
            recent_attempts = [
                record for record in self._recovery_history
                if (record['component_name'] == component_name and
                    datetime.utcnow() - record['recovery_time'] < timedelta(minutes=10))
            ]
            
            # Don't attempt recovery if there were recent failed attempts
            if len(recent_attempts) >= 3:
                logger.info(f"Too many recent recovery attempts for {component_name}, skipping")
                return False
            
            return True
    
    def get_recovery_history(self, component_name: str = None) -> List[Dict[str, Any]]:
        """Get recovery history.
        
        Args:
            component_name: Optional component name to filter by
            
        Returns:
            List of recovery records
        """
        with self._lock:
            if component_name:
                return [
                    record for record in self._recovery_history
                    if record['component_name'] == component_name
                ]
            else:
                return self._recovery_history.copy()
    
    def clear_recovery_history(self) -> None:
        """Clear recovery history."""
        with self._lock:
            self._recovery_history.clear()
            logger.info("Cleared recovery history")


# Convenience function for creating resilience components
def create_resilience_system() -> tuple[HealthChecker, GracefulDegradationManager, SystemRecoveryManager]:
    """Create a complete resilience system.
    
    Returns:
        Tuple of (health_checker, degradation_manager, recovery_manager)
    """
    health_checker = HealthChecker()
    degradation_manager = GracefulDegradationManager(health_checker)
    recovery_manager = SystemRecoveryManager(health_checker, degradation_manager)
    
    return health_checker, degradation_manager, recovery_manager