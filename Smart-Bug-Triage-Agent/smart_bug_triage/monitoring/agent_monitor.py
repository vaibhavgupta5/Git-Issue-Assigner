"""Agent health monitoring and management."""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from smart_bug_triage.database.connection import get_db_session
from smart_bug_triage.models.database import AgentState, SystemAlert
from smart_bug_triage.utils.logging import get_logger


@dataclass
class AgentHealthStatus:
    """Agent health status information."""
    agent_id: str
    agent_type: str
    status: str
    last_heartbeat: Optional[datetime]
    error_count: int
    last_error: Optional[str]
    is_healthy: bool
    uptime_percentage: float
    response_time_ms: Optional[float]


@dataclass
class SystemHealthSummary:
    """Overall system health summary."""
    total_agents: int
    healthy_agents: int
    unhealthy_agents: int
    agents_by_type: Dict[str, int]
    critical_alerts: int
    avg_uptime_percentage: float
    last_updated: datetime


class AgentHealthMonitor:
    """Monitors agent health and generates alerts."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.heartbeat_timeout_minutes = 10  # Consider agent unhealthy after 10 minutes
        self.error_threshold = 5  # Alert after 5 errors
    
    def record_agent_heartbeat(self, agent_id: str, agent_type: str, 
                             status: str = 'active', configuration: Optional[Dict[str, Any]] = None,
                             error_message: Optional[str] = None) -> None:
        """Record agent heartbeat and update status."""
        try:
            with get_db_session() as session:
                agent_state = session.query(AgentState).filter(
                    AgentState.agent_id == agent_id
                ).first()
                
                if agent_state:
                    # Update existing agent
                    agent_state.status = status
                    agent_state.last_heartbeat = datetime.now()
                    agent_state.updated_at = datetime.now()
                    
                    if configuration:
                        agent_state.configuration = configuration
                    
                    if error_message:
                        agent_state.error_count += 1
                        agent_state.last_error = error_message
                        
                        # Check if error threshold exceeded
                        if agent_state.error_count >= self.error_threshold:
                            self._create_agent_alert(
                                agent_id, 'error', 'high',
                                f"Agent {agent_id} has exceeded error threshold ({agent_state.error_count} errors)"
                            )
                    else:
                        # Reset error count on successful heartbeat
                        if agent_state.error_count > 0:
                            agent_state.error_count = 0
                            agent_state.last_error = None
                else:
                    # Create new agent state
                    agent_state = AgentState(
                        agent_id=agent_id,
                        agent_type=agent_type,
                        status=status,
                        configuration=configuration or {},
                        last_heartbeat=datetime.now(),
                        error_count=1 if error_message else 0,
                        last_error=error_message
                    )
                    session.add(agent_state)
                
                session.commit()
                self.logger.debug(f"Recorded heartbeat for agent {agent_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to record agent heartbeat: {str(e)}")
    
    def get_agent_health_status(self, agent_id: str) -> Optional[AgentHealthStatus]:
        """Get health status for a specific agent."""
        try:
            with get_db_session() as session:
                agent_state = session.query(AgentState).filter(
                    AgentState.agent_id == agent_id
                ).first()
                
                if not agent_state:
                    return None
                
                # Calculate if agent is healthy
                is_healthy = self._is_agent_healthy(agent_state)
                
                # Calculate uptime percentage (last 24 hours)
                uptime_percentage = self._calculate_uptime_percentage(agent_id)
                
                return AgentHealthStatus(
                    agent_id=agent_state.agent_id,
                    agent_type=agent_state.agent_type,
                    status=agent_state.status,
                    last_heartbeat=agent_state.last_heartbeat,
                    error_count=agent_state.error_count,
                    last_error=agent_state.last_error,
                    is_healthy=is_healthy,
                    uptime_percentage=uptime_percentage,
                    response_time_ms=None  # Could be calculated from metrics
                )
                
        except Exception as e:
            self.logger.error(f"Failed to get agent health status: {str(e)}")
            return None
    
    def get_all_agents_health(self) -> List[AgentHealthStatus]:
        """Get health status for all agents."""
        try:
            with get_db_session() as session:
                agent_states = session.query(AgentState).all()
                
                health_statuses = []
                for agent_state in agent_states:
                    is_healthy = self._is_agent_healthy(agent_state)
                    uptime_percentage = self._calculate_uptime_percentage(agent_state.agent_id)
                    
                    health_status = AgentHealthStatus(
                        agent_id=agent_state.agent_id,
                        agent_type=agent_state.agent_type,
                        status=agent_state.status,
                        last_heartbeat=agent_state.last_heartbeat,
                        error_count=agent_state.error_count,
                        last_error=agent_state.last_error,
                        is_healthy=is_healthy,
                        uptime_percentage=uptime_percentage,
                        response_time_ms=None
                    )
                    health_statuses.append(health_status)
                
                return health_statuses
                
        except Exception as e:
            self.logger.error(f"Failed to get all agents health: {str(e)}")
            return []
    
    def get_system_health_summary(self) -> SystemHealthSummary:
        """Get overall system health summary."""
        try:
            agent_health_statuses = self.get_all_agents_health()
            
            total_agents = len(agent_health_statuses)
            healthy_agents = len([a for a in agent_health_statuses if a.is_healthy])
            unhealthy_agents = total_agents - healthy_agents
            
            # Count agents by type
            agents_by_type = {}
            for agent in agent_health_statuses:
                agent_type = agent.agent_type
                agents_by_type[agent_type] = agents_by_type.get(agent_type, 0) + 1
            
            # Count critical alerts
            with get_db_session() as session:
                critical_alerts = session.query(SystemAlert).filter(
                    and_(
                        SystemAlert.is_active == True,
                        SystemAlert.severity == 'critical'
                    )
                ).count()
            
            # Calculate average uptime
            uptimes = [a.uptime_percentage for a in agent_health_statuses]
            avg_uptime = sum(uptimes) / len(uptimes) if uptimes else 0.0
            
            return SystemHealthSummary(
                total_agents=total_agents,
                healthy_agents=healthy_agents,
                unhealthy_agents=unhealthy_agents,
                agents_by_type=agents_by_type,
                critical_alerts=critical_alerts,
                avg_uptime_percentage=avg_uptime,
                last_updated=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get system health summary: {str(e)}")
            return SystemHealthSummary(
                total_agents=0,
                healthy_agents=0,
                unhealthy_agents=0,
                agents_by_type={},
                critical_alerts=0,
                avg_uptime_percentage=0.0,
                last_updated=datetime.now()
            )
    
    def check_agent_health_and_alert(self) -> List[str]:
        """Check all agents and create alerts for unhealthy ones."""
        alerts_created = []
        
        try:
            agent_health_statuses = self.get_all_agents_health()
            
            for agent_health in agent_health_statuses:
                if not agent_health.is_healthy:
                    # Determine alert severity and message
                    if agent_health.last_heartbeat is None:
                        severity = 'critical'
                        message = f"Agent {agent_health.agent_id} has never reported a heartbeat"
                    elif agent_health.error_count >= self.error_threshold:
                        severity = 'high'
                        message = f"Agent {agent_health.agent_id} has {agent_health.error_count} errors"
                    else:
                        severity = 'medium'
                        message = f"Agent {agent_health.agent_id} missed heartbeat (last: {agent_health.last_heartbeat})"
                    
                    alert_name = f"agent_health_{agent_health.agent_id}"
                    self._create_agent_alert(agent_health.agent_id, 'health', severity, message)
                    alerts_created.append(alert_name)
            
            return alerts_created
            
        except Exception as e:
            self.logger.error(f"Failed to check agent health: {str(e)}")
            return []
    
    def _is_agent_healthy(self, agent_state: AgentState) -> bool:
        """Determine if an agent is healthy based on its state."""
        # Agent is unhealthy if:
        # 1. Status is 'error' or 'inactive'
        # 2. No heartbeat in the last timeout period
        # 3. Error count exceeds threshold
        
        if agent_state.status in ['error', 'inactive']:
            return False
        
        if agent_state.last_heartbeat is None:
            return False
        
        timeout_threshold = datetime.now() - timedelta(minutes=self.heartbeat_timeout_minutes)
        if agent_state.last_heartbeat < timeout_threshold:
            return False
        
        if agent_state.error_count >= self.error_threshold:
            return False
        
        return True
    
    def _calculate_uptime_percentage(self, agent_id: str, hours: int = 24) -> float:
        """Calculate agent uptime percentage over the specified period."""
        try:
            # This is a simplified calculation
            # In a real implementation, you might track heartbeat intervals
            with get_db_session() as session:
                cutoff_time = datetime.now() - timedelta(hours=hours)
                
                agent_state = session.query(AgentState).filter(
                    AgentState.agent_id == agent_id
                ).first()
                
                if not agent_state or not agent_state.last_heartbeat:
                    return 0.0
                
                # Simple calculation: if last heartbeat is recent, assume good uptime
                if agent_state.last_heartbeat >= cutoff_time:
                    # Calculate based on error count (more errors = lower uptime)
                    error_penalty = min(agent_state.error_count * 5, 50)  # Max 50% penalty
                    return max(100 - error_penalty, 0)
                else:
                    return 0.0
                    
        except Exception as e:
            self.logger.error(f"Failed to calculate uptime for agent {agent_id}: {str(e)}")
            return 0.0
    
    def _create_agent_alert(self, agent_id: str, alert_type: str, severity: str, message: str) -> None:
        """Create an alert for agent issues."""
        try:
            alert_name = f"agent_{alert_type}_{agent_id}"
            
            with get_db_session() as session:
                # Check if alert already exists and is active
                existing_alert = session.query(SystemAlert).filter(
                    and_(
                        SystemAlert.alert_name == alert_name,
                        SystemAlert.is_active == True
                    )
                ).first()
                
                if existing_alert:
                    # Update existing alert
                    existing_alert.message = message
                    existing_alert.triggered_at = datetime.now()
                else:
                    # Create new alert
                    alert = SystemAlert(
                        alert_name=alert_name,
                        alert_type=alert_type,
                        severity=severity,
                        message=message,
                        is_active=True
                    )
                    session.add(alert)
                
                session.commit()
                self.logger.warning(f"Created/updated alert: {alert_name}")
                
        except Exception as e:
            self.logger.error(f"Failed to create agent alert: {str(e)}")
    
    def resolve_agent_alert(self, agent_id: str, alert_type: str) -> None:
        """Resolve an agent alert when the issue is fixed."""
        try:
            alert_name = f"agent_{alert_type}_{agent_id}"
            
            with get_db_session() as session:
                alert = session.query(SystemAlert).filter(
                    and_(
                        SystemAlert.alert_name == alert_name,
                        SystemAlert.is_active == True
                    )
                ).first()
                
                if alert:
                    alert.is_active = False
                    alert.resolved_at = datetime.now()
                    session.commit()
                    self.logger.info(f"Resolved alert: {alert_name}")
                    
        except Exception as e:
            self.logger.error(f"Failed to resolve agent alert: {str(e)}")
    
    def get_agent_performance_metrics(self, agent_id: str, days: int = 7) -> Dict[str, Any]:
        """Get performance metrics for a specific agent."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with get_db_session() as session:
                agent_state = session.query(AgentState).filter(
                    AgentState.agent_id == agent_id
                ).first()
                
                if not agent_state:
                    return {'error': 'Agent not found'}
                
                # Calculate metrics
                uptime_percentage = self._calculate_uptime_percentage(agent_id, days * 24)
                
                return {
                    'agent_id': agent_id,
                    'agent_type': agent_state.agent_type,
                    'uptime_percentage': uptime_percentage,
                    'total_errors': agent_state.error_count,
                    'last_error': agent_state.last_error,
                    'last_heartbeat': agent_state.last_heartbeat.isoformat() if agent_state.last_heartbeat else None,
                    'status': agent_state.status,
                    'period_days': days
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get agent performance metrics: {str(e)}")
            return {'error': str(e)}