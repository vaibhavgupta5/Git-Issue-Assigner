"""System recovery procedures and automated recovery workflows."""

import logging
import time
import subprocess
import psutil
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .resilience import SystemRecoveryManager, HealthChecker


logger = logging.getLogger(__name__)


class RecoveryAction(Enum):
    """Types of recovery actions."""
    RESTART_SERVICE = "restart_service"
    RESTART_AGENT = "restart_agent"
    CLEAR_CACHE = "clear_cache"
    RESET_CONNECTION = "reset_connection"
    SCALE_UP = "scale_up"
    FAILOVER = "failover"
    MANUAL_INTERVENTION = "manual_intervention"


@dataclass
class RecoveryStep:
    """Individual recovery step."""
    action: RecoveryAction
    description: str
    command: Optional[str] = None
    timeout_seconds: int = 30
    required: bool = True
    rollback_command: Optional[str] = None


@dataclass
class RecoveryProcedure:
    """Complete recovery procedure for a component."""
    component_name: str
    description: str
    steps: List[RecoveryStep]
    max_execution_time: int = 300  # 5 minutes
    prerequisites: List[str] = None
    post_recovery_checks: List[Callable] = None


class SystemRecoveryOrchestrator:
    """Orchestrates system recovery procedures."""
    
    def __init__(self, recovery_manager: SystemRecoveryManager, health_checker: HealthChecker):
        """Initialize recovery orchestrator.
        
        Args:
            recovery_manager: System recovery manager
            health_checker: Health checker instance
        """
        self.recovery_manager = recovery_manager
        self.health_checker = health_checker
        self._procedures: Dict[str, RecoveryProcedure] = {}
        self._recovery_log: List[Dict[str, Any]] = []
        
        # Register standard recovery procedures
        self._register_standard_procedures()
    
    def register_recovery_procedure(self, procedure: RecoveryProcedure) -> None:
        """Register a recovery procedure.
        
        Args:
            procedure: Recovery procedure to register
        """
        self._procedures[procedure.component_name] = procedure
        logger.info(f"Registered recovery procedure for: {procedure.component_name}")
    
    def execute_recovery_procedure(self, component_name: str) -> bool:
        """Execute recovery procedure for a component.
        
        Args:
            component_name: Name of the component to recover
            
        Returns:
            True if recovery successful, False otherwise
        """
        procedure = self._procedures.get(component_name)
        if not procedure:
            logger.error(f"No recovery procedure found for component: {component_name}")
            return False
        
        recovery_start = datetime.utcnow()
        executed_steps = []
        
        try:
            logger.info(f"Starting recovery procedure for {component_name}: {procedure.description}")
            
            # Check prerequisites
            if not self._check_prerequisites(procedure):
                logger.error(f"Prerequisites not met for {component_name} recovery")
                return False
            
            # Execute recovery steps
            for i, step in enumerate(procedure.steps):
                step_start = time.time()
                
                try:
                    logger.info(f"Executing step {i+1}/{len(procedure.steps)}: {step.description}")
                    
                    success = self._execute_recovery_step(step)
                    step_duration = time.time() - step_start
                    
                    executed_steps.append({
                        'step_number': i + 1,
                        'action': step.action.value,
                        'description': step.description,
                        'success': success,
                        'duration_seconds': step_duration,
                        'timestamp': datetime.utcnow()
                    })
                    
                    if not success and step.required:
                        logger.error(f"Required recovery step failed: {step.description}")
                        # Attempt rollback
                        self._rollback_steps(executed_steps)
                        return False
                    
                    # Check timeout
                    if (datetime.utcnow() - recovery_start).total_seconds() > procedure.max_execution_time:
                        logger.error(f"Recovery procedure timed out for {component_name}")
                        self._rollback_steps(executed_steps)
                        return False
                        
                except Exception as e:
                    logger.error(f"Error executing recovery step: {e}")
                    executed_steps.append({
                        'step_number': i + 1,
                        'action': step.action.value,
                        'description': step.description,
                        'success': False,
                        'error': str(e),
                        'duration_seconds': time.time() - step_start,
                        'timestamp': datetime.utcnow()
                    })
                    
                    if step.required:
                        self._rollback_steps(executed_steps)
                        return False
            
            # Perform post-recovery checks
            if procedure.post_recovery_checks:
                for check in procedure.post_recovery_checks:
                    if not check():
                        logger.error(f"Post-recovery check failed for {component_name}")
                        return False
            
            # Verify component health
            time.sleep(5)  # Allow time for component to stabilize
            health_status = self.health_checker.check_component_health(component_name)
            
            recovery_duration = (datetime.utcnow() - recovery_start).total_seconds()
            
            # Log recovery attempt
            recovery_record = {
                'component_name': component_name,
                'procedure_description': procedure.description,
                'start_time': recovery_start,
                'duration_seconds': recovery_duration,
                'success': health_status.is_healthy,
                'steps_executed': executed_steps,
                'final_health_status': {
                    'is_healthy': health_status.is_healthy,
                    'error_message': health_status.error_message,
                    'response_time_ms': health_status.response_time_ms
                }
            }
            
            self._recovery_log.append(recovery_record)
            
            if health_status.is_healthy:
                logger.info(f"Recovery successful for {component_name} in {recovery_duration:.2f}s")
                return True
            else:
                logger.error(f"Recovery failed for {component_name}: {health_status.error_message}")
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error during recovery of {component_name}: {e}")
            
            recovery_record = {
                'component_name': component_name,
                'procedure_description': procedure.description,
                'start_time': recovery_start,
                'duration_seconds': (datetime.utcnow() - recovery_start).total_seconds(),
                'success': False,
                'error': str(e),
                'steps_executed': executed_steps
            }
            
            self._recovery_log.append(recovery_record)
            return False
    
    def _check_prerequisites(self, procedure: RecoveryProcedure) -> bool:
        """Check if prerequisites are met for recovery procedure.
        
        Args:
            procedure: Recovery procedure to check
            
        Returns:
            True if prerequisites are met, False otherwise
        """
        if not procedure.prerequisites:
            return True
        
        for prerequisite in procedure.prerequisites:
            # Check if prerequisite component is healthy
            status = self.health_checker.check_component_health(prerequisite)
            if not status.is_healthy:
                logger.error(f"Prerequisite {prerequisite} is not healthy")
                return False
        
        return True
    
    def _execute_recovery_step(self, step: RecoveryStep) -> bool:
        """Execute a single recovery step.
        
        Args:
            step: Recovery step to execute
            
        Returns:
            True if step successful, False otherwise
        """
        try:
            if step.action == RecoveryAction.RESTART_SERVICE:
                return self._restart_service(step)
            elif step.action == RecoveryAction.RESTART_AGENT:
                return self._restart_agent(step)
            elif step.action == RecoveryAction.CLEAR_CACHE:
                return self._clear_cache(step)
            elif step.action == RecoveryAction.RESET_CONNECTION:
                return self._reset_connection(step)
            elif step.action == RecoveryAction.SCALE_UP:
                return self._scale_up(step)
            elif step.action == RecoveryAction.FAILOVER:
                return self._failover(step)
            elif step.action == RecoveryAction.MANUAL_INTERVENTION:
                return self._manual_intervention(step)
            else:
                logger.error(f"Unknown recovery action: {step.action}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing recovery step {step.action}: {e}")
            return False
    
    def _restart_service(self, step: RecoveryStep) -> bool:
        """Restart a system service.
        
        Args:
            step: Recovery step with service restart command
            
        Returns:
            True if restart successful, False otherwise
        """
        if not step.command:
            logger.error("No command specified for service restart")
            return False
        
        try:
            logger.info(f"Restarting service: {step.command}")
            result = subprocess.run(
                step.command.split(),
                timeout=step.timeout_seconds,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("Service restart successful")
                return True
            else:
                logger.error(f"Service restart failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Service restart timed out after {step.timeout_seconds}s")
            return False
        except Exception as e:
            logger.error(f"Error restarting service: {e}")
            return False
    
    def _restart_agent(self, step: RecoveryStep) -> bool:
        """Restart an agent process.
        
        Args:
            step: Recovery step with agent restart information
            
        Returns:
            True if restart successful, False otherwise
        """
        # This would integrate with the agent management system
        logger.info(f"Restarting agent: {step.description}")
        
        # For now, simulate agent restart
        time.sleep(2)
        return True
    
    def _clear_cache(self, step: RecoveryStep) -> bool:
        """Clear system or application cache.
        
        Args:
            step: Recovery step with cache clearing information
            
        Returns:
            True if cache clearing successful, False otherwise
        """
        logger.info(f"Clearing cache: {step.description}")
        
        if step.command:
            try:
                result = subprocess.run(
                    step.command.split(),
                    timeout=step.timeout_seconds,
                    capture_output=True,
                    text=True
                )
                return result.returncode == 0
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")
                return False
        
        return True
    
    def _reset_connection(self, step: RecoveryStep) -> bool:
        """Reset network or database connections.
        
        Args:
            step: Recovery step with connection reset information
            
        Returns:
            True if reset successful, False otherwise
        """
        logger.info(f"Resetting connections: {step.description}")
        
        # This would integrate with connection managers
        time.sleep(1)
        return True
    
    def _scale_up(self, step: RecoveryStep) -> bool:
        """Scale up system resources.
        
        Args:
            step: Recovery step with scaling information
            
        Returns:
            True if scaling successful, False otherwise
        """
        logger.info(f"Scaling up resources: {step.description}")
        
        # This would integrate with container orchestration or cloud services
        time.sleep(3)
        return True
    
    def _failover(self, step: RecoveryStep) -> bool:
        """Perform failover to backup systems.
        
        Args:
            step: Recovery step with failover information
            
        Returns:
            True if failover successful, False otherwise
        """
        logger.info(f"Performing failover: {step.description}")
        
        # This would integrate with load balancers and backup systems
        time.sleep(2)
        return True
    
    def _manual_intervention(self, step: RecoveryStep) -> bool:
        """Handle manual intervention requirement.
        
        Args:
            step: Recovery step requiring manual intervention
            
        Returns:
            True (assumes manual intervention will be performed)
        """
        logger.warning(f"Manual intervention required: {step.description}")
        
        # Send alert to administrators
        self._send_manual_intervention_alert(step)
        
        # For automated recovery, we assume manual intervention will be performed
        return True
    
    def _send_manual_intervention_alert(self, step: RecoveryStep) -> None:
        """Send alert for manual intervention requirement.
        
        Args:
            step: Recovery step requiring manual intervention
        """
        alert_message = f"Manual intervention required: {step.description}"
        logger.critical(alert_message)
        
        # This would integrate with alerting systems (email, Slack, etc.)
    
    def _rollback_steps(self, executed_steps: List[Dict[str, Any]]) -> None:
        """Rollback executed recovery steps.
        
        Args:
            executed_steps: List of executed steps to rollback
        """
        logger.warning("Rolling back recovery steps")
        
        # Rollback in reverse order
        for step_info in reversed(executed_steps):
            if step_info.get('success') and 'rollback_command' in step_info:
                try:
                    rollback_cmd = step_info['rollback_command']
                    if rollback_cmd:
                        logger.info(f"Rolling back step: {step_info['description']}")
                        subprocess.run(rollback_cmd.split(), timeout=30)
                except Exception as e:
                    logger.error(f"Error during rollback: {e}")
    
    def _register_standard_procedures(self) -> None:
        """Register standard recovery procedures for common components."""
        
        # Database recovery procedure
        db_procedure = RecoveryProcedure(
            component_name="database",
            description="Recover database connection and performance",
            steps=[
                RecoveryStep(
                    action=RecoveryAction.RESET_CONNECTION,
                    description="Reset database connections",
                    timeout_seconds=30
                ),
                RecoveryStep(
                    action=RecoveryAction.CLEAR_CACHE,
                    description="Clear database query cache",
                    command="redis-cli FLUSHDB",
                    timeout_seconds=10,
                    required=False
                ),
                RecoveryStep(
                    action=RecoveryAction.RESTART_SERVICE,
                    description="Restart database service if needed",
                    command="sudo systemctl restart postgresql",
                    timeout_seconds=60,
                    required=False
                )
            ]
        )
        self.register_recovery_procedure(db_procedure)
        
        # Message queue recovery procedure
        mq_procedure = RecoveryProcedure(
            component_name="message_queue",
            description="Recover message queue connectivity and processing",
            steps=[
                RecoveryStep(
                    action=RecoveryAction.RESET_CONNECTION,
                    description="Reset RabbitMQ connections",
                    timeout_seconds=30
                ),
                RecoveryStep(
                    action=RecoveryAction.CLEAR_CACHE,
                    description="Purge dead letter queues",
                    timeout_seconds=20,
                    required=False
                ),
                RecoveryStep(
                    action=RecoveryAction.RESTART_SERVICE,
                    description="Restart RabbitMQ service",
                    command="sudo systemctl restart rabbitmq-server",
                    timeout_seconds=90,
                    required=False
                )
            ]
        )
        self.register_recovery_procedure(mq_procedure)
        
        # API service recovery procedure
        api_procedure = RecoveryProcedure(
            component_name="api_service",
            description="Recover external API connectivity",
            steps=[
                RecoveryStep(
                    action=RecoveryAction.RESET_CONNECTION,
                    description="Reset API client connections",
                    timeout_seconds=20
                ),
                RecoveryStep(
                    action=RecoveryAction.CLEAR_CACHE,
                    description="Clear API response cache",
                    timeout_seconds=10,
                    required=False
                ),
                RecoveryStep(
                    action=RecoveryAction.FAILOVER,
                    description="Switch to backup API endpoints",
                    timeout_seconds=30,
                    required=False
                )
            ]
        )
        self.register_recovery_procedure(api_procedure)
        
        # Agent recovery procedure
        agent_procedure = RecoveryProcedure(
            component_name="agent",
            description="Recover failed agent processes",
            steps=[
                RecoveryStep(
                    action=RecoveryAction.RESTART_AGENT,
                    description="Restart agent process",
                    timeout_seconds=30
                ),
                RecoveryStep(
                    action=RecoveryAction.RESET_CONNECTION,
                    description="Reset agent connections",
                    timeout_seconds=20
                ),
                RecoveryStep(
                    action=RecoveryAction.CLEAR_CACHE,
                    description="Clear agent state cache",
                    timeout_seconds=10,
                    required=False
                )
            ]
        )
        self.register_recovery_procedure(agent_procedure)
    
    def get_recovery_log(self, component_name: str = None, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recovery log entries.
        
        Args:
            component_name: Optional component name to filter by
            hours: Number of hours to look back
            
        Returns:
            List of recovery log entries
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        filtered_log = [
            entry for entry in self._recovery_log
            if entry['start_time'] >= cutoff_time
        ]
        
        if component_name:
            filtered_log = [
                entry for entry in filtered_log
                if entry['component_name'] == component_name
            ]
        
        return filtered_log
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery statistics.
        
        Returns:
            Dictionary with recovery statistics
        """
        total_recoveries = len(self._recovery_log)
        successful_recoveries = sum(1 for entry in self._recovery_log if entry['success'])
        
        # Calculate average recovery time
        successful_entries = [entry for entry in self._recovery_log if entry['success']]
        avg_recovery_time = 0
        if successful_entries:
            avg_recovery_time = sum(entry['duration_seconds'] for entry in successful_entries) / len(successful_entries)
        
        # Component-specific statistics
        component_stats = {}
        for entry in self._recovery_log:
            component = entry['component_name']
            if component not in component_stats:
                component_stats[component] = {'total': 0, 'successful': 0}
            
            component_stats[component]['total'] += 1
            if entry['success']:
                component_stats[component]['successful'] += 1
        
        return {
            'total_recovery_attempts': total_recoveries,
            'successful_recoveries': successful_recoveries,
            'success_rate': successful_recoveries / total_recoveries if total_recoveries > 0 else 0,
            'average_recovery_time_seconds': avg_recovery_time,
            'component_statistics': component_stats,
            'registered_procedures': list(self._procedures.keys())
        }
    
    def clear_recovery_log(self) -> None:
        """Clear the recovery log."""
        self._recovery_log.clear()
        logger.info("Recovery log cleared")


def create_system_recovery_orchestrator(recovery_manager: SystemRecoveryManager, health_checker: HealthChecker) -> SystemRecoveryOrchestrator:
    """Create and configure a system recovery orchestrator.
    
    Args:
        recovery_manager: System recovery manager
        health_checker: Health checker instance
        
    Returns:
        Configured SystemRecoveryOrchestrator
    """
    orchestrator = SystemRecoveryOrchestrator(recovery_manager, health_checker)
    
    # Additional custom procedures can be registered here
    
    return orchestrator