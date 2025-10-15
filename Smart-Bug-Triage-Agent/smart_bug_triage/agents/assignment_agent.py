"""Assignment Agent for intelligent bug assignment to developers."""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass

from .base import Agent
from .assignment_algorithm import AssignmentAlgorithm, AssignmentResult, DeveloperScore
from ..api.github_client import GitHubAPIClient
from ..api.jira_client import JiraAPIClient
from ..message_queue.consumer import MessageConsumer, MessageHandler
from ..message_queue.publisher import MessagePublisher
from ..message_queue.serialization import MessageType
from ..models.common import CategorizedBug, DeveloperProfile, DeveloperStatus, Assignment
from ..models.database import (
    Bug, Developer, DeveloperStatus as DBDeveloperStatus, 
    Assignment as DBAssignment, AssignmentFeedback
)
from ..database.connection import DatabaseManager
from ..config.settings import Settings


@dataclass
class AssignmentConfig:
    """Configuration for the Assignment Agent."""
    min_confidence_threshold: float = 0.5
    max_assignment_retries: int = 3
    assignment_timeout: int = 30  # seconds
    enable_github_assignment: bool = True
    enable_jira_assignment: bool = True
    enable_notifications: bool = True
    fallback_to_manual: bool = True


@dataclass
class AssignmentAttempt:
    """Record of an assignment attempt."""
    bug_id: str
    developer_id: str
    attempt_number: int
    timestamp: datetime
    success: bool
    error_message: Optional[str] = None


class AssignmentMessageHandler(MessageHandler):
    """Message handler for processing categorized bugs."""
    
    def __init__(self, assignment_agent: 'AssignmentAgent'):
        self.assignment_agent = assignment_agent
        self.logger = logging.getLogger(__name__)
    
    def handle_message(self, message_data: Any, message_type: MessageType, delivery_tag: str) -> bool:
        """Handle categorized bug messages for assignment.
        
        Args:
            message_data: Categorized bug data
            message_type: Type of message
            delivery_tag: Message delivery tag
            
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            if message_type == MessageType.CATEGORIZED_BUG:
                return self.assignment_agent.process_categorized_bug(message_data)
            else:
                self.logger.warning(f"Unsupported message type: {message_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error handling message {delivery_tag}: {e}")
            return False
    
    def get_supported_message_types(self) -> List[MessageType]:
        """Get supported message types."""
        return [MessageType.CATEGORIZED_BUG]


class AssignmentAgent(Agent):
    """Agent responsible for assigning categorized bugs to appropriate developers."""
    
    def __init__(
        self,
        config: AssignmentConfig,
        github_client: GitHubAPIClient,
        jira_client: Optional[JiraAPIClient],
        db_manager: DatabaseManager,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        settings: Settings
    ):
        """Initialize Assignment Agent.
        
        Args:
            config: Assignment configuration
            github_client: GitHub API client
            jira_client: Optional Jira API client
            db_manager: Database manager
            message_consumer: Message queue consumer
            message_publisher: Message queue publisher
            settings: Application settings
        """
        super().__init__("assignment_agent", {"config": config.__dict__})
        
        self.config = config
        self.github_client = github_client
        self.jira_client = jira_client
        self.db_manager = db_manager
        self.message_consumer = message_consumer
        self.message_publisher = message_publisher
        self.settings = settings
        
        self.logger = logging.getLogger(__name__)
        
        # Assignment algorithm
        self.assignment_algorithm = AssignmentAlgorithm()
        
        # Assignment tracking
        self._assignment_attempts: Dict[str, List[AssignmentAttempt]] = {}
        self._assignment_stats = {
            'total_processed': 0,
            'successful_assignments': 0,
            'failed_assignments': 0,
            'manual_escalations': 0,
            'last_assignment_time': None
        }
        
        # Register message handler
        self.message_handler = AssignmentMessageHandler(self)
        self.message_consumer.register_handler(self.message_handler)
    
    def start(self) -> bool:
        """Start the Assignment Agent."""
        try:
            self.logger.info("Starting Assignment Agent")
            
            # Test API connections
            if not self._test_api_connections():
                self.logger.error("API connection tests failed")
                return False
            
            # Start message consumer
            if not self.message_consumer.start_consuming():
                self.logger.error("Failed to start message consumer")
                return False
            
            self.status = "active"
            self.logger.info("Assignment Agent started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start Assignment Agent: {e}")
            self.status = "error"
            return False
    
    def stop(self) -> bool:
        """Stop the Assignment Agent."""
        try:
            self.logger.info("Stopping Assignment Agent")
            
            # Stop message consumer
            self.message_consumer.stop_consuming()
            
            self.status = "inactive"
            self.logger.info("Assignment Agent stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping Assignment Agent: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "assignment_stats": self._assignment_stats.copy(),
            "consumer_stats": self.message_consumer.get_consume_stats(),
            "publisher_stats": self.message_publisher.get_publish_stats(),
            "config": self.config.__dict__
        }
    
    def process_categorized_bug(self, categorized_bug_data: Dict[str, Any]) -> bool:
        """Process a categorized bug for assignment.
        
        Args:
            categorized_bug_data: Categorized bug data from message queue
            
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            self.logger.info(f"Processing categorized bug: {categorized_bug_data.get('bug_report', {}).get('id')}")
            
            # Convert message data to CategorizedBug object
            categorized_bug = self._convert_message_to_categorized_bug(categorized_bug_data)
            if not categorized_bug:
                self.logger.error("Failed to convert message data to CategorizedBug")
                return False
            
            # Update statistics
            self._assignment_stats['total_processed'] += 1
            
            # Find best developer for assignment
            assignment_result = self._find_best_developer(categorized_bug)
            if not assignment_result:
                self.logger.warning(f"No suitable developer found for bug {categorized_bug.bug_report.id}")
                return self._handle_no_assignment(categorized_bug)
            
            # Execute assignment
            success = self._execute_assignment(categorized_bug, assignment_result)
            
            if success:
                self._assignment_stats['successful_assignments'] += 1
                self._assignment_stats['last_assignment_time'] = datetime.now()
                self.logger.info(
                    f"Successfully assigned bug {categorized_bug.bug_report.id} "
                    f"to developer {assignment_result.developer_id}"
                )
            else:
                self._assignment_stats['failed_assignments'] += 1
                self.logger.error(f"Failed to assign bug {categorized_bug.bug_report.id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error processing categorized bug: {e}")
            self._assignment_stats['failed_assignments'] += 1
            return False
    
    def _convert_message_to_categorized_bug(self, data: Dict[str, Any]) -> Optional[CategorizedBug]:
        """Convert message data to CategorizedBug object.
        
        Args:
            data: Message data dictionary
            
        Returns:
            CategorizedBug object or None if conversion fails
        """
        try:
            # This would typically involve deserializing the message data
            # For now, we'll assume the data structure matches our model
            from ..models.common import BugReport, BugCategory, Priority
            
            bug_report_data = data.get('bug_report', {})
            bug_report = BugReport(
                id=bug_report_data['id'],
                title=bug_report_data['title'],
                description=bug_report_data['description'],
                reporter=bug_report_data['reporter'],
                created_at=datetime.fromisoformat(bug_report_data['created_at']),
                platform=bug_report_data['platform'],
                raw_data=bug_report_data.get('raw_data', {}),
                url=bug_report_data.get('url'),
                labels=bug_report_data.get('labels', [])
            )
            
            categorized_bug = CategorizedBug(
                bug_report=bug_report,
                category=BugCategory(data['category']),
                severity=Priority(data['severity']),
                keywords=data.get('keywords', []),
                confidence_score=data.get('confidence_score', 0.0),
                analysis_timestamp=datetime.fromisoformat(data['analysis_timestamp'])
            )
            
            return categorized_bug
            
        except Exception as e:
            self.logger.error(f"Failed to convert message data: {e}")
            return None
    
    def _find_best_developer(self, categorized_bug: CategorizedBug) -> Optional[AssignmentResult]:
        """Find the best developer for a categorized bug.
        
        Args:
            categorized_bug: The bug to assign
            
        Returns:
            AssignmentResult or None if no suitable developer found
        """
        try:
            with self.db_manager.get_session() as session:
                # Get all developers
                developers = session.query(Developer).all()
                if not developers:
                    self.logger.warning("No developers found in database")
                    return None
                
                # Convert to DeveloperProfile objects
                developer_profiles = []
                for dev in developers:
                    profile = DeveloperProfile(
                        id=dev.id,
                        name=dev.name,
                        github_username=dev.github_username,
                        email=dev.email,
                        skills=dev.skills,
                        experience_level=dev.experience_level,
                        max_capacity=dev.max_capacity,
                        preferred_categories=[cat for cat in dev.preferred_categories] if dev.preferred_categories else [],
                        timezone=dev.timezone
                    )
                    developer_profiles.append(profile)
                
                # Get current developer statuses
                developer_statuses = []
                for dev in developers:
                    db_status = session.query(DBDeveloperStatus).filter_by(
                        developer_id=dev.id
                    ).first()
                    
                    if db_status:
                        from ..models.common import AvailabilityStatus
                        status = DeveloperStatus(
                            developer_id=dev.id,
                            current_workload=db_status.current_workload,
                            open_issues_count=db_status.open_issues_count,
                            complexity_score=db_status.complexity_score,
                            availability=AvailabilityStatus(db_status.availability),
                            calendar_free=db_status.calendar_free,
                            focus_time_active=db_status.focus_time_active,
                            last_activity_timestamp=db_status.last_activity_timestamp,
                            last_updated=db_status.last_updated
                        )
                        developer_statuses.append(status)
                
                # Get feedback history for performance scoring
                feedback_history = {}
                for dev in developers:
                    feedback_list = session.query(AssignmentFeedback).filter_by(
                        developer_id=dev.id
                    ).order_by(AssignmentFeedback.feedback_timestamp.desc()).limit(50).all()
                    feedback_history[dev.id] = feedback_list
                
                # Use assignment algorithm to find best match
                assignment_result = self.assignment_algorithm.find_best_developer(
                    categorized_bug,
                    developer_profiles,
                    developer_statuses,
                    feedback_history
                )
                
                if assignment_result and assignment_result.confidence_score >= self.config.min_confidence_threshold:
                    return assignment_result
                else:
                    self.logger.warning(
                        f"No developer meets confidence threshold {self.config.min_confidence_threshold} "
                        f"for bug {categorized_bug.bug_report.id}"
                    )
                    return None
                
        except Exception as e:
            self.logger.error(f"Error finding best developer: {e}")
            return None
    
    def _execute_assignment(self, categorized_bug: CategorizedBug, assignment_result: AssignmentResult) -> bool:
        """Execute the bug assignment.
        
        Args:
            categorized_bug: The bug to assign
            assignment_result: Assignment decision result
            
        Returns:
            True if assignment successful, False otherwise
        """
        assignment_id = str(uuid.uuid4())
        bug_id = categorized_bug.bug_report.id
        developer_id = assignment_result.developer_id
        
        try:
            # Record assignment attempt
            attempt = AssignmentAttempt(
                bug_id=bug_id,
                developer_id=developer_id,
                attempt_number=len(self._assignment_attempts.get(bug_id, [])) + 1,
                timestamp=datetime.now(),
                success=False
            )
            
            if bug_id not in self._assignment_attempts:
                self._assignment_attempts[bug_id] = []
            self._assignment_attempts[bug_id].append(attempt)
            
            # Get developer info for assignment
            developer = self._get_developer_info(developer_id)
            if not developer:
                attempt.error_message = "Developer not found"
                return False
            
            # Execute assignment in external systems
            assignment_success = False
            
            # Try GitHub assignment
            if self.config.enable_github_assignment and categorized_bug.bug_report.platform == "github":
                assignment_success = self._assign_github_issue(categorized_bug, developer)
            
            # Try Jira assignment
            elif self.config.enable_jira_assignment and categorized_bug.bug_report.platform == "jira":
                assignment_success = self._assign_jira_issue(categorized_bug, developer)
            
            if not assignment_success:
                attempt.error_message = "External system assignment failed"
                return False
            
            # Save assignment to database
            if not self._save_assignment_to_database(
                assignment_id, categorized_bug, assignment_result, developer
            ):
                attempt.error_message = "Database save failed"
                return False
            
            # Send notifications if enabled
            if self.config.enable_notifications:
                self._send_assignment_notification(assignment_id, categorized_bug, developer, assignment_result)
            
            # Update attempt as successful
            attempt.success = True
            
            self.logger.info(
                f"Assignment {assignment_id} completed successfully: "
                f"bug {bug_id} -> developer {developer_id} "
                f"(confidence: {assignment_result.confidence_score:.2f})"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error executing assignment: {e}")
            if self._assignment_attempts.get(bug_id):
                self._assignment_attempts[bug_id][-1].error_message = str(e)
            return False
    
    def _assign_github_issue(self, categorized_bug: CategorizedBug, developer: Developer) -> bool:
        """Assign GitHub issue to developer.
        
        Args:
            categorized_bug: Bug to assign
            developer: Developer to assign to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Parse GitHub URL to get owner/repo/issue_number
            url = categorized_bug.bug_report.url
            if not url:
                self.logger.error("No URL found for GitHub issue")
                return False
            
            # Extract repo info from URL (e.g., https://github.com/owner/repo/issues/123)
            url_parts = url.split('/')
            if len(url_parts) < 7:
                self.logger.error(f"Invalid GitHub URL format: {url}")
                return False
            
            owner = url_parts[3]
            repo = url_parts[4]
            issue_number = int(url_parts[6])
            
            # Assign issue
            success = self.github_client.assign_issue(
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                assignees=[developer.github_username]
            )
            
            if success:
                # Add assignment comment
                comment = (
                    f"🤖 **Automated Assignment**\n\n"
                    f"This issue has been automatically assigned to @{developer.github_username} "
                    f"based on:\n"
                    f"- **Category**: {categorized_bug.category.value}\n"
                    f"- **Priority**: {categorized_bug.severity.value}\n"
                    f"- **Keywords**: {', '.join(categorized_bug.keywords[:5])}\n"
                    f"- **Confidence**: {categorized_bug.confidence_score:.1%}\n\n"
                    f"*Assignment made by Smart Bug Triage System*"
                )
                
                self.github_client.add_comment(owner, repo, issue_number, comment)
                
                # Add category label
                category_label = f"category:{categorized_bug.category.value}"
                priority_label = f"priority:{categorized_bug.severity.value}"
                self.github_client.add_labels(owner, repo, issue_number, [category_label, priority_label])
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to assign GitHub issue: {e}")
            return False
    
    def _assign_jira_issue(self, categorized_bug: CategorizedBug, developer: Developer) -> bool:
        """Assign Jira issue to developer.
        
        Args:
            categorized_bug: Bug to assign
            developer: Developer to assign to
            
        Returns:
            True if successful, False otherwise
        """
        if not self.jira_client:
            self.logger.error("Jira client not available")
            return False
        
        try:
            # Extract issue key from URL or use bug ID
            issue_key = categorized_bug.bug_report.id
            
            # Get developer's Jira account ID (this would need to be stored in developer profile)
            # For now, we'll use email to find the user
            jira_users = self.jira_client.search_users(developer.email, max_results=1)
            if not jira_users:
                self.logger.error(f"Jira user not found for email: {developer.email}")
                return False
            
            jira_user = jira_users[0]
            
            # Assign issue
            success = self.jira_client.assign_issue(issue_key, jira_user.account_id)
            
            if success:
                # Add assignment comment
                comment = (
                    f"🤖 *Automated Assignment*\n\n"
                    f"This issue has been automatically assigned to {developer.name} "
                    f"based on:\n"
                    f"• Category: {categorized_bug.category.value}\n"
                    f"• Priority: {categorized_bug.severity.value}\n"
                    f"• Keywords: {', '.join(categorized_bug.keywords[:5])}\n"
                    f"• Confidence: {categorized_bug.confidence_score:.1%}\n\n"
                    f"_Assignment made by Smart Bug Triage System_"
                )
                
                self.jira_client.add_comment(issue_key, comment)
                
                # Add labels
                labels = [
                    f"auto-category-{categorized_bug.category.value}",
                    f"auto-priority-{categorized_bug.severity.value}"
                ]
                self.jira_client.add_labels(issue_key, labels)
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to assign Jira issue: {e}")
            return False
    
    def _save_assignment_to_database(
        self,
        assignment_id: str,
        categorized_bug: CategorizedBug,
        assignment_result: AssignmentResult,
        developer: Developer
    ) -> bool:
        """Save assignment record to database.
        
        Args:
            assignment_id: Unique assignment ID
            categorized_bug: The assigned bug
            assignment_result: Assignment algorithm result
            developer: Assigned developer
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db_manager.get_session() as session:
                # Create assignment record
                assignment = DBAssignment(
                    id=assignment_id,
                    bug_id=categorized_bug.bug_report.id,
                    developer_id=developer.id,
                    assigned_at=datetime.now(),
                    assignment_reason=assignment_result.reasoning,
                    confidence_score=assignment_result.confidence_score,
                    status="active"
                )
                
                session.add(assignment)
                
                # Update developer workload
                developer_status = session.query(DBDeveloperStatus).filter_by(
                    developer_id=developer.id
                ).first()
                
                if developer_status:
                    developer_status.current_workload += 1
                    developer_status.open_issues_count += 1
                    developer_status.last_updated = datetime.now()
                
                session.commit()
                
                self.logger.debug(f"Saved assignment {assignment_id} to database")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to save assignment to database: {e}")
            return False
    
    def _send_assignment_notification(
        self,
        assignment_id: str,
        categorized_bug: CategorizedBug,
        developer: Developer,
        assignment_result: AssignmentResult
    ) -> None:
        """Send assignment notification.
        
        Args:
            assignment_id: Assignment ID
            categorized_bug: Assigned bug
            developer: Assigned developer
            assignment_result: Assignment result
        """
        try:
            notification_data = {
                "type": "bug_assignment",
                "assignment_id": assignment_id,
                "bug": {
                    "id": categorized_bug.bug_report.id,
                    "title": categorized_bug.bug_report.title,
                    "category": categorized_bug.category.value,
                    "severity": categorized_bug.severity.value,
                    "url": categorized_bug.bug_report.url
                },
                "developer": {
                    "id": developer.id,
                    "name": developer.name,
                    "email": developer.email,
                    "github_username": developer.github_username
                },
                "assignment_reason": assignment_result.reasoning,
                "confidence_score": assignment_result.confidence_score,
                "timestamp": datetime.now().isoformat()
            }
            
            # Publish notification message
            self.message_publisher.publish_notification(notification_data)
            
            self.logger.debug(f"Sent assignment notification for {assignment_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to send assignment notification: {e}")
    
    def _get_developer_info(self, developer_id: str) -> Optional[Developer]:
        """Get developer information from database.
        
        Args:
            developer_id: Developer ID
            
        Returns:
            Developer object or None if not found
        """
        try:
            with self.db_manager.get_session() as session:
                developer = session.query(Developer).filter_by(id=developer_id).first()
                if developer:
                    # Detach from session
                    session.expunge(developer)
                return developer
                
        except Exception as e:
            self.logger.error(f"Failed to get developer info: {e}")
            return None
    
    def _handle_no_assignment(self, categorized_bug: CategorizedBug) -> bool:
        """Handle case where no suitable developer is found.
        
        Args:
            categorized_bug: Bug that couldn't be assigned
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            if self.config.fallback_to_manual:
                # Escalate to manual assignment
                self._escalate_to_manual_assignment(categorized_bug)
                self._assignment_stats['manual_escalations'] += 1
                return True
            else:
                self.logger.warning(f"No assignment fallback configured for bug {categorized_bug.bug_report.id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error handling no assignment: {e}")
            return False
    
    def _escalate_to_manual_assignment(self, categorized_bug: CategorizedBug) -> None:
        """Escalate bug to manual assignment.
        
        Args:
            categorized_bug: Bug to escalate
        """
        try:
            escalation_data = {
                "type": "manual_assignment_required",
                "bug": {
                    "id": categorized_bug.bug_report.id,
                    "title": categorized_bug.bug_report.title,
                    "category": categorized_bug.category.value,
                    "severity": categorized_bug.severity.value,
                    "url": categorized_bug.bug_report.url,
                    "confidence_score": categorized_bug.confidence_score
                },
                "reason": "No suitable developer found with sufficient confidence",
                "timestamp": datetime.now().isoformat()
            }
            
            # Publish escalation notification
            self.message_publisher.publish_system_event(escalation_data, priority=8)
            
            self.logger.info(f"Escalated bug {categorized_bug.bug_report.id} to manual assignment")
            
        except Exception as e:
            self.logger.error(f"Failed to escalate to manual assignment: {e}")
    
    def _test_api_connections(self) -> bool:
        """Test API connections.
        
        Returns:
            True if all enabled APIs are working, False otherwise
        """
        try:
            # Test GitHub connection
            if self.config.enable_github_assignment:
                if not self.github_client.test_connection():
                    self.logger.error("GitHub API connection test failed")
                    return False
            
            # Test Jira connection if enabled and available
            if self.config.enable_jira_assignment and self.jira_client:
                if not self.jira_client.test_connection():
                    self.logger.error("Jira API connection test failed")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"API connection test failed: {e}")
            return False
    
    def get_assignment_history(self, bug_id: Optional[str] = None, developer_id: Optional[str] = None) -> List[Dict]:
        """Get assignment history.
        
        Args:
            bug_id: Optional bug ID filter
            developer_id: Optional developer ID filter
            
        Returns:
            List of assignment records
        """
        try:
            with self.db_manager.get_session() as session:
                query = session.query(DBAssignment)
                
                if bug_id:
                    query = query.filter_by(bug_id=bug_id)
                
                if developer_id:
                    query = query.filter_by(developer_id=developer_id)
                
                assignments = query.order_by(DBAssignment.assigned_at.desc()).limit(100).all()
                
                result = []
                for assignment in assignments:
                    result.append({
                        "id": assignment.id,
                        "bug_id": assignment.bug_id,
                        "developer_id": assignment.developer_id,
                        "assigned_at": assignment.assigned_at.isoformat(),
                        "assignment_reason": assignment.assignment_reason,
                        "confidence_score": assignment.confidence_score,
                        "status": assignment.status,
                        "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None
                    })
                
                return result
                
        except Exception as e:
            self.logger.error(f"Failed to get assignment history: {e}")
            return []
    
    def get_assignment_attempts(self, bug_id: str) -> List[AssignmentAttempt]:
        """Get assignment attempts for a bug.
        
        Args:
            bug_id: Bug ID
            
        Returns:
            List of assignment attempts
        """
        return self._assignment_attempts.get(bug_id, [])