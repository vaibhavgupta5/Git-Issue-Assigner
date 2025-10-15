"""Individual developer agent and agent manager."""

import logging
import threading
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Timer, Lock

from .base import Agent
from .performance_tracker import PerformanceTracker, PerformanceMetrics, SkillConfidence
from .calendar_integration import CalendarIntegration, GoogleCalendarProvider, OutlookCalendarProvider
from ..api.github_client import GitHubAPIClient
from ..api.jira_client import JiraAPIClient
from ..models.common import DeveloperStatus, AvailabilityStatus, WorkloadInfo
from ..models.database import Developer, DeveloperStatus as DBDeveloperStatus, AgentState, AssignmentFeedback
from ..database.connection import DatabaseManager
from ..config.settings import Settings


@dataclass
class DeveloperAgentConfig:
    """Configuration for a developer agent."""
    developer_id: str
    github_username: str
    update_interval: int = 900  # 15 minutes in seconds
    max_retries: int = 3
    retry_delay: int = 60  # 1 minute
    enable_calendar_integration: bool = True
    calendar_provider: Optional[str] = None  # "google" or "outlook"
    performance_tracking_enabled: bool = True


class DeveloperAgent(Agent):
    """Individual agent that monitors a specific developer's status and workload."""
    
    def __init__(
        self,
        config: DeveloperAgentConfig,
        github_client: GitHubAPIClient,
        jira_client: Optional[JiraAPIClient],
        db_manager: DatabaseManager,
        settings: Settings,
        calendar_integration: Optional[CalendarIntegration] = None
    ):
        """Initialize developer agent.
        
        Args:
            config: Agent configuration
            github_client: GitHub API client
            jira_client: Optional Jira API client
            db_manager: Database manager
            settings: Application settings
            calendar_integration: Optional calendar integration
        """
        super().__init__(f"developer_{config.developer_id}", "developer")
        
        self.config = config
        self.github_client = github_client
        self.jira_client = jira_client
        self.db_manager = db_manager
        self.settings = settings
        self.calendar_integration = calendar_integration
        
        self.logger = logging.getLogger(f"{__name__}.{config.github_username}")
        
        # Agent state
        self._running = False
        self._update_timer: Optional[Timer] = None
        self._lock = Lock()
        self._error_count = 0
        self._last_successful_update: Optional[datetime] = None
        
        # Cache developer profile
        self._developer_profile: Optional[Developer] = None
        
        # Performance tracking
        self._performance_tracker: Optional[PerformanceTracker] = None
        self._last_performance_metrics: Optional[PerformanceMetrics] = None
        self._last_skill_confidence: Optional[SkillConfidence] = None
    
    def start(self) -> bool:
        """Start the developer agent."""
        with self._lock:
            if self._running:
                self.logger.warning("Agent is already running")
                return False
            
            try:
                # Load developer profile
                self._developer_profile = self._load_developer_profile()
                if not self._developer_profile:
                    self.logger.error(f"Developer profile not found for {self.config.github_username}")
                    return False
                
                # Initialize performance tracker if enabled
                if self.config.performance_tracking_enabled:
                    with self.db_manager.get_session() as session:
                        self._performance_tracker = PerformanceTracker(session)
                
                # Update agent state in database
                self._update_agent_state("active")
                
                self._running = True
                self.logger.info(f"Starting developer agent for {self.config.github_username}")
                
                # Start monitoring loop
                self._schedule_next_update()
                
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to start agent: {e}")
                return False
    
    def stop(self) -> bool:
        """Stop the developer agent."""
        with self._lock:
            if not self._running:
                return True
            
            self._running = False
            
            # Cancel scheduled update
            if self._update_timer:
                self._update_timer.cancel()
                self._update_timer = None
            
            # Update agent state
            self._update_agent_state("inactive")
            
            self.logger.info(f"Stopped developer agent for {self.config.github_username}")
            return True
    
    def process_message(self, message: Dict) -> bool:
        """Process incoming messages (not used for developer agents)."""
        return True
    
    def get_status(self) -> Dict:
        """Get current agent status."""
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "running": self._running,
                "developer_id": self.config.developer_id,
                "github_username": self.config.github_username,
                "error_count": self._error_count,
                "last_successful_update": self._last_successful_update.isoformat() if self._last_successful_update else None,
                "next_update": self._get_next_update_time()
            }
    
    def _load_developer_profile(self) -> Optional[Developer]:
        """Load developer profile from database."""
        try:
            with self.db_manager.get_session() as session:
                developer = session.query(Developer).filter_by(
                    id=self.config.developer_id
                ).first()
                
                if developer:
                    # Detach from session to use in other threads
                    session.expunge(developer)
                
                return developer
                
        except Exception as e:
            self.logger.error(f"Failed to load developer profile: {e}")
            return None
    
    def _schedule_next_update(self):
        """Schedule the next status update."""
        if not self._running:
            return
        
        self._update_timer = Timer(self.config.update_interval, self._update_status)
        self._update_timer.start()
    
    def _update_status(self):
        """Update developer status by polling external APIs."""
        if not self._running:
            return
        
        try:
            self.logger.debug(f"Updating status for {self.config.github_username}")
            
            # Get current workload from APIs
            workload_info = self._get_current_workload()
            
            # Get availability status
            availability = self._check_availability()
            
            # Check calendar status
            calendar_free, focus_time_active = self._check_calendar_status()
            
            # Update performance metrics if enabled
            if self.config.performance_tracking_enabled and self._performance_tracker:
                self._update_performance_metrics()
            
            # Create status update
            status = DeveloperStatus(
                developer_id=self.config.developer_id,
                current_workload=workload_info.total_issues,
                open_issues_count=workload_info.total_issues,
                complexity_score=workload_info.estimated_hours,
                availability=availability,
                calendar_free=calendar_free,
                focus_time_active=focus_time_active,
                last_activity_timestamp=datetime.now(),
                last_updated=datetime.now()
            )
            
            # Save to database
            self._save_status_to_database(status)
            
            # Update success tracking
            with self._lock:
                self._last_successful_update = datetime.now()
                self._error_count = 0
            
            # Update agent heartbeat
            self._update_agent_state("active")
            
            self.logger.debug(
                f"Status updated for {self.config.github_username}: "
                f"workload={workload_info.total_issues}, availability={availability.value}"
            )
            
        except Exception as e:
            with self._lock:
                self._error_count += 1
            
            self.logger.error(f"Failed to update status: {e}")
            
            # Update agent state to error if too many failures
            if self._error_count >= self.config.max_retries:
                self._update_agent_state("error", str(e))
        
        finally:
            # Schedule next update
            self._schedule_next_update()
    
    def _get_current_workload(self) -> WorkloadInfo:
        """Get current workload from GitHub and Jira APIs."""
        total_issues = 0
        complexity_breakdown = {}
        estimated_hours = 0.0
        
        try:
            # Get GitHub assigned issues
            github_issues = self.github_client.get_user_assigned_issues(
                self.config.github_username, state="open"
            )
            
            total_issues += len(github_issues)
            
            # Analyze GitHub issues for complexity
            github_complexity = self._analyze_github_complexity(github_issues)
            complexity_breakdown.update(github_complexity)
            estimated_hours += sum(github_complexity.values())
            
            # Get Jira assigned issues if client is available
            if self.jira_client:
                try:
                    jira_issues = self.jira_client.get_user_assigned_issues(
                        self.config.github_username, status="open"
                    )
                    
                    total_issues += len(jira_issues)
                    
                    # Analyze Jira issues for complexity
                    jira_complexity = self._analyze_jira_complexity(jira_issues)
                    complexity_breakdown.update(jira_complexity)
                    estimated_hours += sum(jira_complexity.values())
                    
                except Exception as e:
                    self.logger.warning(f"Failed to get Jira issues: {e}")
            
        except Exception as e:
            self.logger.error(f"Failed to get workload: {e}")
        
        # Calculate capacity utilization
        max_capacity = self._developer_profile.max_capacity if self._developer_profile else 10
        capacity_utilization = min(total_issues / max_capacity, 1.0) if max_capacity > 0 else 0.0
        
        return WorkloadInfo(
            total_issues=total_issues,
            complexity_breakdown=complexity_breakdown,
            estimated_hours=estimated_hours,
            capacity_utilization=capacity_utilization
        )
    
    def _analyze_github_complexity(self, issues) -> Dict[str, float]:
        """Analyze GitHub issues for complexity scoring."""
        complexity = {}
        
        for issue in issues:
            issue_complexity = 1.0  # Base complexity
            
            # Increase complexity based on labels
            for label in issue.labels:
                label_lower = label.lower()
                if any(keyword in label_lower for keyword in ['critical', 'urgent', 'high']):
                    issue_complexity += 2.0
                elif any(keyword in label_lower for keyword in ['complex', 'difficult', 'epic']):
                    issue_complexity += 1.5
                elif any(keyword in label_lower for keyword in ['bug', 'defect']):
                    issue_complexity += 0.5
            
            # Increase complexity based on title/description length
            text_length = len(issue.title) + len(issue.body)
            if text_length > 1000:
                issue_complexity += 1.0
            elif text_length > 500:
                issue_complexity += 0.5
            
            complexity[f"github_{issue.number}"] = issue_complexity
        
        return complexity
    
    def _analyze_jira_complexity(self, issues) -> Dict[str, float]:
        """Analyze Jira issues for complexity scoring."""
        complexity = {}
        
        for issue in issues:
            # Use story points if available, otherwise estimate
            issue_complexity = getattr(issue, 'story_points', 2.0)
            
            # Adjust based on priority
            priority = getattr(issue, 'priority', 'Medium')
            if priority in ['Critical', 'Highest']:
                issue_complexity += 2.0
            elif priority in ['High', 'Major']:
                issue_complexity += 1.0
            
            complexity[f"jira_{issue.key}"] = issue_complexity
        
        return complexity
    
    def _check_availability(self) -> AvailabilityStatus:
        """Check developer availability status."""
        if not self._developer_profile:
            return AvailabilityStatus.UNAVAILABLE
        
        # Check calendar availability first if integration is enabled
        if (self.config.enable_calendar_integration and 
            self.calendar_integration and 
            self._developer_profile.email):
            
            try:
                calendar_status = self.calendar_integration.check_availability(
                    self._developer_profile.email
                )
                
                # If calendar shows busy or focus time, respect that
                if calendar_status in [AvailabilityStatus.BUSY, AvailabilityStatus.FOCUS_TIME]:
                    return calendar_status
                    
            except Exception as e:
                self.logger.warning(f"Failed to check calendar availability: {e}")
        
        # Fall back to workload-based availability
        try:
            with self.db_manager.get_session() as session:
                status = session.query(DBDeveloperStatus).filter_by(
                    developer_id=self.config.developer_id
                ).first()
                
                if status:
                    # Check if overloaded
                    if status.current_workload >= self._developer_profile.max_capacity:
                        return AvailabilityStatus.BUSY
                    elif status.current_workload >= self._developer_profile.max_capacity * 0.8:
                        return AvailabilityStatus.BUSY
                    else:
                        return AvailabilityStatus.AVAILABLE
                
        except Exception as e:
            self.logger.error(f"Failed to check availability: {e}")
        
        return AvailabilityStatus.AVAILABLE
    
    def _save_status_to_database(self, status: DeveloperStatus):
        """Save developer status to database."""
        try:
            with self.db_manager.get_session() as session:
                # Update or create status record
                db_status = session.query(DBDeveloperStatus).filter_by(
                    developer_id=status.developer_id
                ).first()
                
                if db_status:
                    # Update existing record
                    db_status.current_workload = status.current_workload
                    db_status.open_issues_count = status.open_issues_count
                    db_status.complexity_score = status.complexity_score
                    db_status.availability = status.availability.value
                    db_status.calendar_free = status.calendar_free
                    db_status.focus_time_active = status.focus_time_active
                    db_status.last_activity_timestamp = status.last_activity_timestamp
                    db_status.last_updated = status.last_updated
                else:
                    # Create new record
                    db_status = DBDeveloperStatus(
                        developer_id=status.developer_id,
                        current_workload=status.current_workload,
                        open_issues_count=status.open_issues_count,
                        complexity_score=status.complexity_score,
                        availability=status.availability.value,
                        calendar_free=status.calendar_free,
                        focus_time_active=status.focus_time_active,
                        last_activity_timestamp=status.last_activity_timestamp,
                        last_updated=status.last_updated
                    )
                    session.add(db_status)
                
                session.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to save status to database: {e}")
            raise
    
    def _update_agent_state(self, status: str, error_message: Optional[str] = None):
        """Update agent state in database."""
        try:
            with self.db_manager.get_session() as session:
                agent_state = session.query(AgentState).filter_by(
                    agent_id=self.agent_id
                ).first()
                
                if agent_state:
                    agent_state.status = status
                    agent_state.last_heartbeat = datetime.now()
                    agent_state.updated_at = datetime.now()
                    
                    if error_message:
                        agent_state.error_count += 1
                        agent_state.last_error = error_message
                    elif status == "active":
                        agent_state.error_count = 0
                        agent_state.last_error = None
                else:
                    agent_state = AgentState(
                        agent_id=self.agent_id,
                        agent_type=self.agent_type,
                        status=status,
                        configuration={
                            "developer_id": self.config.developer_id,
                            "github_username": self.config.github_username,
                            "update_interval": self.config.update_interval
                        },
                        last_heartbeat=datetime.now(),
                        error_count=1 if error_message else 0,
                        last_error=error_message
                    )
                    session.add(agent_state)
                
                session.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to update agent state: {e}")
    
    def _check_calendar_status(self) -> Tuple[bool, bool]:
        """Check calendar status for availability and focus time.
        
        Returns:
            Tuple of (calendar_free, focus_time_active)
        """
        if (not self.config.enable_calendar_integration or 
            not self.calendar_integration or 
            not self._developer_profile or 
            not self._developer_profile.email):
            return True, False  # Default to free if no calendar integration
        
        try:
            # Check current availability
            status = self.calendar_integration.check_availability(
                self._developer_profile.email
            )
            
            calendar_free = status == AvailabilityStatus.AVAILABLE
            focus_time_active = status == AvailabilityStatus.FOCUS_TIME
            
            return calendar_free, focus_time_active
            
        except Exception as e:
            self.logger.warning(f"Failed to check calendar status: {e}")
            return True, False  # Default to free on error
    
    def _update_performance_metrics(self) -> None:
        """Update performance metrics and skill confidence."""
        if not self._performance_tracker:
            return
        
        try:
            with self.db_manager.get_session() as session:
                # Update performance tracker session
                self._performance_tracker.db_session = session
                
                # Calculate performance metrics
                self._last_performance_metrics = self._performance_tracker.calculate_performance_metrics(
                    self.config.developer_id
                )
                
                # Calculate skill confidence
                self._last_skill_confidence = self._performance_tracker.calculate_skill_confidence(
                    self.config.developer_id
                )
                
                self.logger.debug(
                    f"Updated performance metrics for {self.config.github_username}: "
                    f"success_rate={self._last_performance_metrics.success_rate:.1f}%, "
                    f"avg_resolution_time={self._last_performance_metrics.average_resolution_time:.1f}h"
                )
                
        except Exception as e:
            self.logger.error(f"Failed to update performance metrics: {e}")
    
    def process_assignment_feedback(self, assignment_id: str, feedback: AssignmentFeedback) -> None:
        """Process feedback for an assignment to update performance metrics.
        
        Args:
            assignment_id: Assignment ID
            feedback: Assignment feedback
        """
        if not self.config.performance_tracking_enabled or not self._performance_tracker:
            return
        
        try:
            with self.db_manager.get_session() as session:
                self._performance_tracker.db_session = session
                self._performance_tracker.update_performance_from_feedback(
                    self.config.developer_id,
                    assignment_id,
                    feedback
                )
                
                # Recalculate metrics after feedback
                self._update_performance_metrics()
                
                self.logger.info(
                    f"Processed feedback for assignment {assignment_id}, "
                    f"rating: {feedback.rating}/5, appropriate: {feedback.was_appropriate}"
                )
                
        except Exception as e:
            self.logger.error(f"Failed to process assignment feedback: {e}")
    
    def get_performance_metrics(self) -> Optional[PerformanceMetrics]:
        """Get current performance metrics.
        
        Returns:
            Performance metrics or None if not available
        """
        return self._last_performance_metrics
    
    def get_skill_confidence(self) -> Optional[SkillConfidence]:
        """Get current skill confidence scores.
        
        Returns:
            Skill confidence or None if not available
        """
        return self._last_skill_confidence
    
    def get_detailed_status(self) -> Dict:
        """Get detailed agent status including performance metrics.
        
        Returns:
            Detailed status dictionary
        """
        base_status = self.get_status()
        
        # Add performance metrics if available
        if self._last_performance_metrics:
            base_status["performance_metrics"] = {
                "total_assignments": self._last_performance_metrics.total_assignments,
                "success_rate": self._last_performance_metrics.success_rate,
                "average_resolution_time": self._last_performance_metrics.average_resolution_time,
                "feedback_score": self._last_performance_metrics.feedback_score,
                "workload_efficiency": self._last_performance_metrics.workload_efficiency,
                "recent_trend": self._last_performance_metrics.recent_trend
            }
        
        # Add skill confidence if available
        if self._last_skill_confidence:
            base_status["skill_confidence"] = {
                "top_skills": dict(sorted(
                    self._last_skill_confidence.skill_scores.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]),  # Top 5 skills
                "category_confidence": {
                    cat.value: score for cat, score in self._last_skill_confidence.category_confidence.items()
                }
            }
        
        # Add calendar status if available
        if self.config.enable_calendar_integration and self.calendar_integration:
            calendar_free, focus_time_active = self._check_calendar_status()
            base_status["calendar_status"] = {
                "calendar_free": calendar_free,
                "focus_time_active": focus_time_active,
                "integration_enabled": True
            }
        else:
            base_status["calendar_status"] = {
                "integration_enabled": False
            }
        
        return base_status
    
    def _get_next_update_time(self) -> Optional[str]:
        """Get the next scheduled update time."""
        if self._update_timer and self._running:
            # Estimate next update time
            next_time = datetime.now() + timedelta(seconds=self.config.update_interval)
            return next_time.isoformat()
        return None


class DeveloperAgentManager:
    """Manager for all developer agents with lifecycle management and health monitoring."""
    
    def __init__(
        self,
        github_client: GitHubAPIClient,
        jira_client: Optional[JiraAPIClient],
        db_manager: DatabaseManager,
        settings: Settings,
        calendar_integration: Optional[CalendarIntegration] = None
    ):
        """Initialize the developer agent manager.
        
        Args:
            github_client: GitHub API client
            jira_client: Optional Jira API client
            db_manager: Database manager
            settings: Application settings
            calendar_integration: Optional calendar integration
        """
        self.github_client = github_client
        self.jira_client = jira_client
        self.db_manager = db_manager
        self.settings = settings
        self.calendar_integration = calendar_integration
        
        self.logger = logging.getLogger(__name__)
        
        # Agent registry
        self._agents: Dict[str, DeveloperAgent] = {}
        self._agent_health: Dict[str, Dict] = {}
        self._lock = Lock()
        
        # Health monitoring
        self._health_check_interval = 300  # 5 minutes
        self._health_timer: Optional[Timer] = None
        self._running = False
        
        # Agent restart tracking
        self._restart_attempts: Dict[str, int] = {}
        self._max_restart_attempts = 3
        self._restart_cooldown = 600  # 10 minutes
    
    def start(self) -> bool:
        """Start the agent manager."""
        with self._lock:
            if self._running:
                return True
            
            try:
                self.logger.info("Starting developer agent manager")
                
                # Discover and create agents for all developers
                self._discover_and_create_agents()
                
                # Start health monitoring
                self._running = True
                self._schedule_health_check()
                
                self.logger.info(f"Started agent manager with {len(self._agents)} agents")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to start agent manager: {e}")
                return False
    
    def stop(self) -> bool:
        """Stop the agent manager and all agents."""
        with self._lock:
            if not self._running:
                return True
            
            self._running = False
            
            # Cancel health check timer
            if self._health_timer:
                self._health_timer.cancel()
                self._health_timer = None
            
            # Stop all agents
            for agent in self._agents.values():
                agent.stop()
            
            self._agents.clear()
            
            self.logger.info("Stopped developer agent manager")
            return True
    
    def _discover_and_create_agents(self):
        """Discover developers and create agents for them."""
        try:
            with self.db_manager.get_session() as session:
                developers = session.query(Developer).all()
                
                self.logger.info(f"Discovered {len(developers)} developers in database")
                
                created_count = 0
                for developer in developers:
                    if self._create_agent_for_developer(developer):
                        created_count += 1
                
                self.logger.info(f"Successfully created {created_count} developer agents")
                
        except Exception as e:
            self.logger.error(f"Failed to discover developers: {e}")
            raise
    
    def _create_agent_for_developer(self, developer: Developer) -> bool:
        """Create and start an agent for a developer.
        
        Args:
            developer: Developer database record
            
        Returns:
            True if successful, False otherwise
        """
        try:
            agent_id = f"developer_{developer.id}"
            
            # Skip if agent already exists
            if agent_id in self._agents:
                self.logger.debug(f"Agent already exists for developer {developer.github_username}")
                return True
            
            # Create agent configuration
            config = DeveloperAgentConfig(
                developer_id=developer.id,
                github_username=developer.github_username,
                update_interval=getattr(self.settings, 'developer_agent_update_interval', 900),
                enable_calendar_integration=True,
                performance_tracking_enabled=True
            )
            
            # Create and start agent
            agent = DeveloperAgent(
                config=config,
                github_client=self.github_client,
                jira_client=self.jira_client,
                db_manager=self.db_manager,
                settings=self.settings,
                calendar_integration=self.calendar_integration
            )
            
            # Start the agent
            if agent.start():
                with self._lock:
                    self._agents[agent_id] = agent
                    self._agent_health[agent_id] = {
                        "last_health_check": datetime.now(),
                        "consecutive_failures": 0,
                        "last_restart": None
                    }
                    # Reset restart attempts on successful creation
                    self._restart_attempts.pop(agent_id, None)
                
                self.logger.info(f"Created and started agent for developer: {developer.github_username}")
                return True
            else:
                self.logger.error(f"Failed to start agent for developer: {developer.github_username}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to create agent for developer {developer.github_username}: {e}")
            return False
    
    def add_developer_agent(self, developer_id: str) -> bool:
        """Add an agent for a newly discovered developer.
        
        Args:
            developer_id: Developer ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db_manager.get_session() as session:
                developer = session.query(Developer).filter_by(id=developer_id).first()
                
                if developer:
                    # Detach from session to use in other threads
                    session.expunge(developer)
                    return self._create_agent_for_developer(developer)
                else:
                    self.logger.error(f"Developer not found: {developer_id}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to add developer agent: {e}")
            return False
    
    def spawn_agent_for_new_developer(self, developer_profile: Developer) -> bool:
        """Spawn an agent for a newly discovered developer.
        
        This method is called when the developer discovery process finds a new developer.
        
        Args:
            developer_profile: Developer profile from discovery
            
        Returns:
            True if agent was created successfully
        """
        try:
            self.logger.info(f"Spawning agent for newly discovered developer: {developer_profile.github_username}")
            
            if self._create_agent_for_developer(developer_profile):
                self.logger.info(f"Successfully spawned agent for {developer_profile.github_username}")
                return True
            else:
                self.logger.error(f"Failed to spawn agent for {developer_profile.github_username}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to spawn agent for new developer {developer_profile.github_username}: {e}")
            return False
    
    def remove_developer_agent(self, developer_id: str) -> bool:
        """Remove an agent for a developer.
        
        Args:
            developer_id: Developer ID
            
        Returns:
            True if successful, False otherwise
        """
        agent_id = f"developer_{developer_id}"
        
        with self._lock:
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                agent.stop()
                del self._agents[agent_id]
                self.logger.info(f"Removed agent for developer: {developer_id}")
                return True
            
            return False
    
    def get_all_developer_statuses(self) -> List[DeveloperStatus]:
        """Get current status for all developers.
        
        Returns:
            List of developer statuses
        """
        statuses = []
        
        try:
            with self.db_manager.get_session() as session:
                db_statuses = session.query(DBDeveloperStatus).all()
                
                for db_status in db_statuses:
                    status = DeveloperStatus(
                        developer_id=db_status.developer_id,
                        current_workload=db_status.current_workload,
                        open_issues_count=db_status.open_issues_count,
                        complexity_score=db_status.complexity_score,
                        availability=AvailabilityStatus(db_status.availability),
                        calendar_free=db_status.calendar_free,
                        focus_time_active=db_status.focus_time_active,
                        last_activity_timestamp=db_status.last_activity_timestamp or datetime.now(),
                        last_updated=db_status.last_updated
                    )
                    statuses.append(status)
                    
        except Exception as e:
            self.logger.error(f"Failed to get developer statuses: {e}")
        
        return statuses
    
    def get_agent_health_status(self) -> Dict[str, Dict]:
        """Get health status for all agents.
        
        Returns:
            Dictionary of agent health information
        """
        health_status = {}
        
        with self._lock:
            for agent_id, agent in self._agents.items():
                health_status[agent_id] = agent.get_status()
        
        return health_status
    
    def _schedule_health_check(self):
        """Schedule the next health check."""
        if not self._running:
            return
        
        self._health_timer = Timer(self._health_check_interval, self._perform_health_check)
        self._health_timer.start()
    
    def _perform_health_check(self):
        """Perform comprehensive health check on all agents."""
        if not self._running:
            return
        
        try:
            self.logger.debug("Performing agent health check")
            
            # Check for failed agents and restart them
            failed_agents = []
            unhealthy_agents = []
            
            with self._lock:
                for agent_id, agent in self._agents.items():
                    try:
                        status = agent.get_status()
                        health_info = self._agent_health.get(agent_id, {})
                        
                        # Update health tracking
                        self._agent_health[agent_id] = {
                            "last_health_check": datetime.now(),
                            "consecutive_failures": health_info.get("consecutive_failures", 0),
                            "last_restart": health_info.get("last_restart")
                        }
                        
                        # Check for high error count
                        if status["error_count"] >= 3:
                            self.logger.warning(f"Agent {agent_id} has high error count ({status['error_count']})")
                            failed_agents.append(agent_id)
                        
                        # Check if agent is not running when it should be
                        elif not status["running"]:
                            self.logger.warning(f"Agent {agent_id} is not running")
                            failed_agents.append(agent_id)
                        
                        # Check for stale heartbeat (no updates in last 10 minutes)
                        elif status.get("last_successful_update"):
                            last_update = datetime.fromisoformat(status["last_successful_update"])
                            if datetime.now() - last_update > timedelta(minutes=10):
                                self.logger.warning(f"Agent {agent_id} has stale heartbeat")
                                unhealthy_agents.append(agent_id)
                        
                    except Exception as e:
                        self.logger.error(f"Failed to check health of agent {agent_id}: {e}")
                        failed_agents.append(agent_id)
            
            # Restart failed agents
            for agent_id in failed_agents:
                self._restart_agent_with_backoff(agent_id)
            
            # Try to recover unhealthy agents (less aggressive than restart)
            for agent_id in unhealthy_agents:
                self._attempt_agent_recovery(agent_id)
            
            # Check for new developers that need agents
            self._check_for_new_developers()
            
            # Clean up old restart attempt records
            self._cleanup_restart_attempts()
            
            # Log health summary
            total_agents = len(self._agents)
            healthy_agents = total_agents - len(failed_agents) - len(unhealthy_agents)
            self.logger.debug(
                f"Health check complete: {healthy_agents}/{total_agents} agents healthy, "
                f"{len(failed_agents)} failed, {len(unhealthy_agents)} unhealthy"
            )
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
        
        finally:
            # Schedule next health check
            self._schedule_health_check()
    
    def _restart_agent_with_backoff(self, agent_id: str):
        """Restart a failed agent with exponential backoff.
        
        Args:
            agent_id: Agent ID to restart
        """
        try:
            # Check restart attempts
            attempts = self._restart_attempts.get(agent_id, 0)
            
            if attempts >= self._max_restart_attempts:
                self.logger.error(
                    f"Agent {agent_id} has exceeded maximum restart attempts ({self._max_restart_attempts}). "
                    "Manual intervention required."
                )
                return
            
            # Check cooldown period
            health_info = self._agent_health.get(agent_id, {})
            last_restart = health_info.get("last_restart")
            
            if last_restart and datetime.now() - last_restart < timedelta(seconds=self._restart_cooldown):
                self.logger.debug(f"Agent {agent_id} is in restart cooldown period")
                return
            
            with self._lock:
                if agent_id in self._agents:
                    agent = self._agents[agent_id]
                    developer_id = agent.config.developer_id
                    
                    self.logger.info(f"Restarting agent {agent_id} (attempt {attempts + 1}/{self._max_restart_attempts})")
                    
                    # Stop the failed agent
                    try:
                        agent.stop()
                    except Exception as e:
                        self.logger.warning(f"Error stopping failed agent {agent_id}: {e}")
                    
                    # Remove from registry
                    del self._agents[agent_id]
                    
                    # Update restart tracking
                    self._restart_attempts[agent_id] = attempts + 1
                    self._agent_health[agent_id]["last_restart"] = datetime.now()
                    
                    # Create a new agent
                    if self.add_developer_agent(developer_id):
                        self.logger.info(f"Successfully restarted agent: {agent_id}")
                    else:
                        self.logger.error(f"Failed to restart agent: {agent_id}")
                    
        except Exception as e:
            self.logger.error(f"Failed to restart agent {agent_id}: {e}")
    
    def _attempt_agent_recovery(self, agent_id: str):
        """Attempt to recover an unhealthy agent without full restart.
        
        Args:
            agent_id: Agent ID to recover
        """
        try:
            with self._lock:
                if agent_id in self._agents:
                    agent = self._agents[agent_id]
                    
                    self.logger.info(f"Attempting recovery for unhealthy agent: {agent_id}")
                    
                    # Try to trigger a manual status update
                    try:
                        agent._update_status()
                        self.logger.info(f"Recovery successful for agent: {agent_id}")
                    except Exception as e:
                        self.logger.warning(f"Recovery failed for agent {agent_id}, will restart: {e}")
                        self._restart_agent_with_backoff(agent_id)
                        
        except Exception as e:
            self.logger.error(f"Failed to recover agent {agent_id}: {e}")
    
    def _cleanup_restart_attempts(self):
        """Clean up old restart attempt records."""
        try:
            current_time = datetime.now()
            cleanup_threshold = timedelta(hours=24)  # Clean up attempts older than 24 hours
            
            agents_to_cleanup = []
            for agent_id, health_info in self._agent_health.items():
                last_restart = health_info.get("last_restart")
                if last_restart and current_time - last_restart > cleanup_threshold:
                    agents_to_cleanup.append(agent_id)
            
            for agent_id in agents_to_cleanup:
                self._restart_attempts.pop(agent_id, None)
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup restart attempts: {e}")
    
    def _check_for_new_developers(self):
        """Check for new developers that need agents and remove agents for deleted developers."""
        try:
            with self.db_manager.get_session() as session:
                developers = session.query(Developer).all()
                
                # Get current developer IDs from database
                current_developer_ids = {dev.id for dev in developers}
                
                # Check for new developers that need agents
                new_developers = []
                for developer in developers:
                    agent_id = f"developer_{developer.id}"
                    
                    if agent_id not in self._agents:
                        new_developers.append(developer)
                
                # Create agents for new developers
                for developer in new_developers:
                    self.logger.info(f"Found new developer without agent: {developer.github_username}")
                    # Detach from session to use in other threads
                    session.expunge(developer)
                    if self._create_agent_for_developer(developer):
                        self.logger.info(f"Created agent for new developer: {developer.github_username}")
                
                # Check for agents that no longer have corresponding developers
                with self._lock:
                    agents_to_remove = []
                    for agent_id, agent in self._agents.items():
                        developer_id = agent.config.developer_id
                        if developer_id not in current_developer_ids:
                            agents_to_remove.append((agent_id, developer_id))
                    
                    # Remove orphaned agents
                    for agent_id, developer_id in agents_to_remove:
                        self.logger.info(f"Removing agent for deleted developer: {developer_id}")
                        try:
                            self._agents[agent_id].stop()
                            del self._agents[agent_id]
                            self._agent_health.pop(agent_id, None)
                            self._restart_attempts.pop(agent_id, None)
                        except Exception as e:
                            self.logger.error(f"Error removing orphaned agent {agent_id}: {e}")
                        
        except Exception as e:
            self.logger.error(f"Failed to check for new developers: {e}")
    
    def process_assignment_feedback(self, developer_id: str, assignment_id: str, feedback: AssignmentFeedback) -> bool:
        """Process assignment feedback for a developer agent.
        
        Args:
            developer_id: Developer ID
            assignment_id: Assignment ID
            feedback: Assignment feedback
            
        Returns:
            True if feedback was processed successfully
        """
        agent_id = f"developer_{developer_id}"
        
        with self._lock:
            if agent_id in self._agents:
                try:
                    agent = self._agents[agent_id]
                    agent.process_assignment_feedback(assignment_id, feedback)
                    self.logger.info(f"Processed feedback for developer {developer_id}, assignment {assignment_id}")
                    return True
                except Exception as e:
                    self.logger.error(f"Failed to process feedback for developer {developer_id}: {e}")
                    return False
            else:
                self.logger.warning(f"No agent found for developer {developer_id}")
                return False
    
    def get_developer_performance_metrics(self, developer_id: str) -> Optional[Dict]:
        """Get performance metrics for a specific developer.
        
        Args:
            developer_id: Developer ID
            
        Returns:
            Performance metrics dictionary or None
        """
        agent_id = f"developer_{developer_id}"
        
        with self._lock:
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                metrics = agent.get_performance_metrics()
                skill_confidence = agent.get_skill_confidence()
                
                if metrics and skill_confidence:
                    return {
                        "performance_metrics": {
                            "total_assignments": metrics.total_assignments,
                            "completed_assignments": metrics.completed_assignments,
                            "success_rate": metrics.success_rate,
                            "average_resolution_time": metrics.average_resolution_time,
                            "feedback_score": metrics.feedback_score,
                            "workload_efficiency": metrics.workload_efficiency,
                            "recent_trend": metrics.recent_trend,
                            "category_performance": {cat.value: score for cat, score in metrics.category_performance.items()},
                            "priority_performance": {pri.value: score for pri, score in metrics.priority_performance.items()}
                        },
                        "skill_confidence": {
                            "skill_scores": skill_confidence.skill_scores,
                            "category_confidence": {cat.value: score for cat, score in skill_confidence.category_confidence.items()},
                            "learning_velocity": skill_confidence.learning_velocity
                        }
                    }
            
            return None
    
    def get_all_performance_metrics(self) -> Dict[str, Dict]:
        """Get performance metrics for all developers.
        
        Returns:
            Dictionary mapping developer IDs to their performance metrics
        """
        all_metrics = {}
        
        with self._lock:
            for agent_id, agent in self._agents.items():
                developer_id = agent.config.developer_id
                metrics = self.get_developer_performance_metrics(developer_id)
                if metrics:
                    all_metrics[developer_id] = metrics
        
        return all_metrics
    
    def get_agent_registry_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the agent registry.
        
        Returns:
            Dictionary with registry status information
        """
        with self._lock:
            total_agents = len(self._agents)
            running_agents = sum(1 for agent in self._agents.values() if agent.get_status()["running"])
            
            # Calculate health statistics
            healthy_agents = 0
            error_agents = 0
            
            for agent in self._agents.values():
                status = agent.get_status()
                if status["error_count"] == 0 and status["running"]:
                    healthy_agents += 1
                elif status["error_count"] > 0:
                    error_agents += 1
            
            return {
                "total_agents": total_agents,
                "running_agents": running_agents,
                "healthy_agents": healthy_agents,
                "error_agents": error_agents,
                "manager_running": self._running,
                "health_check_interval": self._health_check_interval,
                "restart_attempts": dict(self._restart_attempts),
                "agent_health_summary": {
                    agent_id: {
                        "consecutive_failures": health.get("consecutive_failures", 0),
                        "last_restart": health.get("last_restart").isoformat() if health.get("last_restart") else None
                    }
                    for agent_id, health in self._agent_health.items()
                }
            }
    
    def force_restart_agent(self, developer_id: str) -> bool:
        """Force restart an agent, bypassing cooldown and attempt limits.
        
        Args:
            developer_id: Developer ID whose agent to restart
            
        Returns:
            True if restart was successful
        """
        agent_id = f"developer_{developer_id}"
        
        try:
            with self._lock:
                if agent_id in self._agents:
                    agent = self._agents[agent_id]
                    
                    self.logger.info(f"Force restarting agent: {agent_id}")
                    
                    # Stop the agent
                    try:
                        agent.stop()
                    except Exception as e:
                        self.logger.warning(f"Error stopping agent during force restart {agent_id}: {e}")
                    
                    # Remove from registry
                    del self._agents[agent_id]
                    
                    # Reset tracking
                    self._restart_attempts.pop(agent_id, None)
                    self._agent_health[agent_id] = {
                        "last_health_check": datetime.now(),
                        "consecutive_failures": 0,
                        "last_restart": datetime.now()
                    }
                    
                    # Create new agent
                    if self.add_developer_agent(developer_id):
                        self.logger.info(f"Successfully force restarted agent: {agent_id}")
                        return True
                    else:
                        self.logger.error(f"Failed to create new agent during force restart: {agent_id}")
                        return False
                else:
                    self.logger.warning(f"Agent not found for force restart: {agent_id}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to force restart agent {agent_id}: {e}")
            return False
    
    def pause_agent(self, developer_id: str) -> bool:
        """Pause an agent temporarily.
        
        Args:
            developer_id: Developer ID whose agent to pause
            
        Returns:
            True if pause was successful
        """
        agent_id = f"developer_{developer_id}"
        
        try:
            with self._lock:
                if agent_id in self._agents:
                    agent = self._agents[agent_id]
                    if agent.stop():
                        self.logger.info(f"Paused agent: {agent_id}")
                        return True
                    else:
                        self.logger.error(f"Failed to pause agent: {agent_id}")
                        return False
                else:
                    self.logger.warning(f"Agent not found for pause: {agent_id}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to pause agent {agent_id}: {e}")
            return False
    
    def resume_agent(self, developer_id: str) -> bool:
        """Resume a paused agent.
        
        Args:
            developer_id: Developer ID whose agent to resume
            
        Returns:
            True if resume was successful
        """
        agent_id = f"developer_{developer_id}"
        
        try:
            with self._lock:
                if agent_id in self._agents:
                    agent = self._agents[agent_id]
                    if agent.start():
                        self.logger.info(f"Resumed agent: {agent_id}")
                        return True
                    else:
                        self.logger.error(f"Failed to resume agent: {agent_id}")
                        return False
                else:
                    self.logger.warning(f"Agent not found for resume: {agent_id}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to resume agent {agent_id}: {e}")
            return False