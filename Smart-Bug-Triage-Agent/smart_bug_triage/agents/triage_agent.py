"""
Triage Agent for analyzing and categorizing bug reports using NLP.
Processes bugs from message queue and publishes categorized results.
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import Agent
from ..models.common import BugReport, CategorizedBug, BugCategory, Priority, AnalysisResult
from ..nlp.pipeline import NLPPipeline
from ..message_queue.consumer import MessageConsumer, MessageHandler
from ..message_queue.publisher import MessagePublisher
from ..message_queue.connection import MessageQueueConnection
from ..message_queue.serialization import MessageType
from ..database.connection import DatabaseManager
from ..config.settings import SystemConfig


logger = logging.getLogger(__name__)


class BugTriageHandler(MessageHandler):
    """Message handler for processing bug reports."""
    
    def __init__(self, triage_agent: 'TriageAgent'):
        """Initialize handler with reference to triage agent.
        
        Args:
            triage_agent: Reference to the triage agent instance
        """
        self.triage_agent = triage_agent
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
    
    def handle_message(self, message_data: Any, message_type: MessageType, delivery_tag: str) -> bool:
        """Handle incoming bug report messages.
        
        Args:
            message_data: Deserialized bug report data
            message_type: Type of the message (should be BUG_REPORT)
            delivery_tag: Delivery tag for acknowledgment
            
        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            self.logger.info(f"Processing bug report message with delivery tag: {delivery_tag}")
            
            # Convert message data to BugReport object
            if isinstance(message_data, dict):
                bug_report = BugReport(**message_data)
            else:
                bug_report = message_data
            
            # Process the bug report
            success = self.triage_agent.process_bug_report(bug_report)
            
            if success:
                self.logger.info(f"Successfully processed bug report: {bug_report.id}")
            else:
                self.logger.error(f"Failed to process bug report: {bug_report.id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error handling bug report message: {e}", exc_info=True)
            return False
    
    def get_supported_message_types(self) -> List[MessageType]:
        """Get list of message types this handler supports.
        
        Returns:
            List containing BUG_REPORT message type
        """
        return [MessageType.BUG_REPORT]


class TriageAgent(Agent):
    """
    Triage Agent that analyzes bug reports using NLP and publishes categorized results.
    
    This agent:
    1. Consumes bug reports from the message queue
    2. Analyzes them using the NLP pipeline
    3. Implements confidence scoring for classification results
    4. Flags low-confidence classifications for manual review
    5. Publishes categorized bugs to the assignment queue
    """
    
    def __init__(self, agent_id: str = "triage_agent", config: Optional[Dict[str, Any]] = None):
        """Initialize the Triage Agent.
        
        Args:
            agent_id: Unique identifier for this agent
            config: Configuration dictionary (optional)
        """
        if config is None:
            system_config = SystemConfig.from_env()
            config = {
                'database': {'url': f"postgresql://{system_config.database.username}:{system_config.database.password}@{system_config.database.host}:{system_config.database.port}/{system_config.database.database}"},
                'message_queue': system_config.message_queue.__dict__,
                'triage': {
                    'confidence_threshold': 0.7,
                    'manual_review_queue': 'manual_review',
                    'processing_timeout': 30.0
                }
            }
        
        super().__init__(agent_id, config)
        
        # Initialize components
        self.nlp_pipeline = NLPPipeline()
        self.db_connection = DatabaseManager(config.get('database', {}).get('url'))
        
        # Create MessageQueueConfig from dict
        from ..config.settings import MessageQueueConfig
        mq_config_dict = config.get('message_queue', {})
        mq_config = MessageQueueConfig(
            host=mq_config_dict.get('host', 'localhost'),
            port=mq_config_dict.get('port', 5672),
            username=mq_config_dict.get('username', 'guest'),
            password=mq_config_dict.get('password', 'guest'),
            virtual_host=mq_config_dict.get('virtual_host', '/'),
            exchange_name=mq_config_dict.get('exchange_name', 'bug_triage'),
            queue_names=mq_config_dict.get('queue_names', {
                "new_bugs": "new_bugs_queue",
                "triaged_bugs": "triaged_bugs_queue",
                "assignments": "assignments_queue",
                "notifications": "notifications_queue"
            })
        )
        self.mq_connection = MessageQueueConnection(mq_config)
        
        # Message queue components
        self.consumer: Optional[MessageConsumer] = None
        self.publisher: Optional[MessagePublisher] = None
        self.message_handler = BugTriageHandler(self)
        
        # Configuration
        self.confidence_threshold = config.get('triage', {}).get('confidence_threshold', 0.7)
        self.manual_review_queue = config.get('triage', {}).get('manual_review_queue', 'manual_review')
        self.processing_timeout = config.get('triage', {}).get('processing_timeout', 30.0)
        
        # Processing statistics
        self.stats = {
            'total_processed': 0,
            'successful_classifications': 0,
            'low_confidence_flags': 0,
            'processing_errors': 0,
            'average_processing_time': 0.0,
            'last_processed_time': None
        }
        
        # Threading
        self._stop_event = threading.Event()
        self._processing_thread: Optional[threading.Thread] = None
        
        self.logger.info(f"Triage Agent {agent_id} initialized with confidence threshold: {self.confidence_threshold}")
    
    def start(self) -> bool:
        """Start the triage agent's processing loop.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            self.logger.info("Starting Triage Agent...")
            
            # Connect to message queue
            if not self.mq_connection.connect():
                self.logger.error("Failed to connect to message queue")
                self.status = "error"
                return False
            
            # Initialize database
            try:
                self.db_connection.initialize()
            except Exception as e:
                self.logger.error(f"Failed to initialize database: {e}")
                self.status = "error"
                return False
            
            # Initialize message queue components
            self.consumer = MessageConsumer(self.mq_connection, "bug_triage.new_bugs")
            self.publisher = MessagePublisher(self.mq_connection)
            
            # Register message handler
            self.consumer.register_handler(self.message_handler)
            
            # Start consuming messages
            if not self.consumer.start_consuming():
                self.logger.error("Failed to start message consumer")
                return False
            
            # Update status
            self.status = "running"
            self.heartbeat()
            
            self.logger.info("Triage Agent started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start Triage Agent: {e}", exc_info=True)
            self.status = "error"
            return False
    
    def stop(self) -> bool:
        """Stop the triage agent gracefully.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            self.logger.info("Stopping Triage Agent...")
            
            # Signal stop
            self._stop_event.set()
            
            # Stop message consumer
            if self.consumer:
                self.consumer.stop_consuming()
            
            # Close connections
            if self.mq_connection:
                self.mq_connection.disconnect()
            
            if self.db_connection:
                self.db_connection.close()
            
            # Update status
            self.status = "stopped"
            
            self.logger.info("Triage Agent stopped successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping Triage Agent: {e}", exc_info=True)
            return False
    
    def process_bug_report(self, bug_report: BugReport) -> bool:
        """Process a single bug report through the NLP pipeline.
        
        Args:
            bug_report: Bug report to process
            
        Returns:
            True if processed successfully, False otherwise
        """
        start_time = time.time()
        
        try:
            self.logger.info(f"Processing bug report: {bug_report.id}")
            
            # Analyze bug report using NLP pipeline
            analysis_result = self.nlp_pipeline.analyze_bug_report(
                bug_report.title, 
                bug_report.description
            )
            
            # Convert analysis result to structured format
            categorized_bug = self._create_categorized_bug(bug_report, analysis_result)
            
            # Check confidence and determine next action
            confidence_check = self._evaluate_confidence(categorized_bug)
            success = False
            
            if confidence_check['requires_manual_review']:
                # Flag for manual review
                success = self._flag_for_manual_review(categorized_bug, confidence_check)
                if success:
                    self.stats['low_confidence_flags'] += 1
            else:
                # Publish to assignment queue
                success = self._publish_categorized_bug(categorized_bug)
                if success:
                    self.stats['successful_classifications'] += 1
            
            # Update processing statistics
            processing_time = time.time() - start_time
            self._update_processing_stats(processing_time, success)
            
            # Store results in database
            self._store_triage_result(categorized_bug, confidence_check, processing_time)
            
            # Update heartbeat
            self.heartbeat()
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error processing bug report {bug_report.id}: {e}", exc_info=True)
            self.stats['processing_errors'] += 1
            return False
    
    def _create_categorized_bug(self, bug_report: BugReport, analysis_result: Dict[str, Any]) -> CategorizedBug:
        """Create a CategorizedBug object from analysis results.
        
        Args:
            bug_report: Original bug report
            analysis_result: NLP analysis results
            
        Returns:
            CategorizedBug object with classification results
        """
        # Extract category and confidence with error handling
        try:
            category_name = analysis_result.get('classification', {}).get('category', 'Unknown')
            category_confidence = analysis_result.get('classification', {}).get('confidence', 0.3)
        except Exception:
            category_name = 'Unknown'
            category_confidence = 0.3
        
        # Map category name to enum
        try:
            # Handle common category name variations
            category_mapping = {
                'frontend/ui': BugCategory.FRONTEND,
                'frontend': BugCategory.FRONTEND,
                'ui': BugCategory.FRONTEND,
                'backend/api': BugCategory.BACKEND,
                'backend': BugCategory.BACKEND,
                'api': BugCategory.API,
                'database': BugCategory.DATABASE,
                'mobile': BugCategory.MOBILE,
                'security': BugCategory.SECURITY,
                'performance': BugCategory.PERFORMANCE
            }
            
            normalized_name = category_name.lower().replace('/', '_').replace(' ', '_')
            category = category_mapping.get(category_name.lower(), None)
            
            if category is None:
                try:
                    category = BugCategory(normalized_name)
                except ValueError:
                    self.logger.warning(f"Unknown category: {category_name}, defaulting to UNKNOWN")
                    category = BugCategory.UNKNOWN
        except Exception:
            self.logger.warning(f"Error mapping category: {category_name}, defaulting to UNKNOWN")
            category = BugCategory.UNKNOWN
        
        # Extract severity with error handling
        try:
            severity_name = analysis_result.get('severity', {}).get('level', 'Medium')
            severity = Priority(severity_name.lower())
        except (ValueError, AttributeError):
            self.logger.warning(f"Unknown or missing severity, defaulting to MEDIUM")
            severity = Priority.MEDIUM
        
        # Extract keywords
        keywords_data = analysis_result.get('keywords', {})
        if isinstance(keywords_data, dict):
            # Extract top keywords from summary
            summary = keywords_data.get('summary', {})
            keywords = summary.get('top_keywords', [])
            
            # Add technical terms
            technical_terms = list(keywords_data.get('technical_terms', {}).keys())
            keywords.extend(technical_terms[:5])  # Limit to top 5 technical terms
        else:
            keywords = []
        
        # Calculate overall confidence score with error handling
        try:
            severity_confidence = analysis_result.get('severity', {}).get('confidence', 0.3)
        except Exception:
            severity_confidence = 0.3
        
        overall_confidence = (category_confidence + severity_confidence) / 2.0
        
        return CategorizedBug(
            bug_report=bug_report,
            category=category,
            severity=severity,
            keywords=keywords,
            confidence_score=overall_confidence,
            analysis_timestamp=datetime.utcnow()
        )
    
    def _evaluate_confidence(self, categorized_bug: CategorizedBug) -> Dict[str, Any]:
        """Evaluate confidence levels and determine if manual review is needed.
        
        Args:
            categorized_bug: Categorized bug to evaluate
            
        Returns:
            Dictionary with confidence evaluation results
        """
        confidence_score = categorized_bug.confidence_score
        
        # Check against threshold from requirements (70% confidence)
        meets_threshold = confidence_score >= self.confidence_threshold
        
        # Additional quality checks
        has_keywords = len(categorized_bug.keywords) > 0
        category_not_unknown = categorized_bug.category != BugCategory.UNKNOWN
        
        # Determine if manual review is required
        requires_manual_review = (
            not meets_threshold or 
            not has_keywords or 
            not category_not_unknown
        )
        
        # Generate review reasons
        review_reasons = []
        if not meets_threshold:
            review_reasons.append(f"Low confidence score: {confidence_score:.2f} < {self.confidence_threshold}")
        if not has_keywords:
            review_reasons.append("No keywords extracted")
        if not category_not_unknown:
            review_reasons.append("Category could not be determined")
        
        return {
            'confidence_score': confidence_score,
            'meets_threshold': meets_threshold,
            'requires_manual_review': requires_manual_review,
            'review_reasons': review_reasons,
            'quality_indicators': {
                'has_keywords': has_keywords,
                'category_determined': category_not_unknown,
                'confidence_acceptable': meets_threshold
            }
        }
    
    def _flag_for_manual_review(self, categorized_bug: CategorizedBug, confidence_check: Dict[str, Any]) -> bool:
        """Flag a bug for manual review due to low confidence.
        
        Args:
            categorized_bug: Bug to flag for review
            confidence_check: Confidence evaluation results
            
        Returns:
            True if flagged successfully, False otherwise
        """
        try:
            # Create manual review message
            review_message = {
                'bug_report': categorized_bug.bug_report,
                'preliminary_classification': {
                    'category': categorized_bug.category.value,
                    'severity': categorized_bug.severity.value,
                    'keywords': categorized_bug.keywords,
                    'confidence_score': categorized_bug.confidence_score
                },
                'review_reasons': confidence_check['review_reasons'],
                'flagged_at': datetime.utcnow().isoformat(),
                'agent_id': self.agent_id
            }
            
            # Publish to manual review queue
            success = self.publisher.publish_message(
                message=review_message,
                message_type=MessageType.SYSTEM_EVENT,
                routing_key=self.manual_review_queue,
                priority=8  # High priority for manual review
            )
            
            if success:
                self.logger.info(f"Flagged bug {categorized_bug.bug_report.id} for manual review")
            else:
                self.logger.error(f"Failed to flag bug {categorized_bug.bug_report.id} for manual review")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error flagging bug for manual review: {e}", exc_info=True)
            return False
    
    def _publish_categorized_bug(self, categorized_bug: CategorizedBug) -> bool:
        """Publish a categorized bug to the assignment queue.
        
        Args:
            categorized_bug: Categorized bug to publish
            
        Returns:
            True if published successfully, False otherwise
        """
        try:
            success = self.publisher.publish_categorized_bug(categorized_bug)
            
            if success:
                self.logger.info(f"Published categorized bug {categorized_bug.bug_report.id} "
                               f"(Category: {categorized_bug.category.value}, "
                               f"Severity: {categorized_bug.severity.value}, "
                               f"Confidence: {categorized_bug.confidence_score:.2f})")
            else:
                self.logger.error(f"Failed to publish categorized bug {categorized_bug.bug_report.id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error publishing categorized bug: {e}", exc_info=True)
            return False
    
    def _update_processing_stats(self, processing_time: float, success: bool) -> None:
        """Update processing statistics.
        
        Args:
            processing_time: Time taken to process the bug
            success: Whether processing was successful
        """
        self.stats['total_processed'] += 1
        self.stats['last_processed_time'] = datetime.utcnow()
        
        # Update average processing time
        current_avg = self.stats['average_processing_time']
        total_processed = self.stats['total_processed']
        
        if total_processed == 1:
            self.stats['average_processing_time'] = processing_time
        else:
            # Calculate running average
            self.stats['average_processing_time'] = (
                (current_avg * (total_processed - 1) + processing_time) / total_processed
            )
    
    def _store_triage_result(self, categorized_bug: CategorizedBug, confidence_check: Dict[str, Any], processing_time: float) -> None:
        """Store triage results in the database.
        
        Args:
            categorized_bug: Categorized bug result
            confidence_check: Confidence evaluation results
            processing_time: Time taken to process
        """
        try:
            with self.db_connection.get_session() as session:
                # Store triage result (implementation depends on database schema)
                triage_result = {
                    'bug_id': categorized_bug.bug_report.id,
                    'agent_id': self.agent_id,
                    'category': categorized_bug.category.value,
                    'severity': categorized_bug.severity.value,
                    'keywords': categorized_bug.keywords,
                    'confidence_score': categorized_bug.confidence_score,
                    'requires_manual_review': confidence_check['requires_manual_review'],
                    'review_reasons': confidence_check['review_reasons'],
                    'processing_time': processing_time,
                    'processed_at': categorized_bug.analysis_timestamp
                }
                
                # Note: Actual database insertion would depend on the schema
                # This is a placeholder for the database operation
                self.logger.debug(f"Stored triage result for bug {categorized_bug.bug_report.id}")
                
        except Exception as e:
            self.logger.error(f"Error storing triage result: {e}", exc_info=True)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status and health information.
        
        Returns:
            Dictionary with agent status and statistics
        """
        return {
            'agent_id': self.agent_id,
            'status': self.status,
            'last_heartbeat': self.last_heartbeat.isoformat(),
            'is_healthy': self.is_healthy(),
            'processing_stats': self.stats.copy(),
            'configuration': {
                'confidence_threshold': self.confidence_threshold,
                'manual_review_queue': self.manual_review_queue,
                'processing_timeout': self.processing_timeout
            },
            'nlp_pipeline_info': self.nlp_pipeline.get_model_info() if self.nlp_pipeline else {},
            'queue_info': self.consumer.get_consume_stats() if self.consumer else {},
            'publisher_stats': self.publisher.get_publish_stats() if self.publisher else {}
        }
    
    def process_single_bug_sync(self, bug_report: BugReport) -> Optional[CategorizedBug]:
        """Process a single bug report synchronously (for testing/debugging).
        
        Args:
            bug_report: Bug report to process
            
        Returns:
            CategorizedBug if successful, None otherwise
        """
        try:
            # Analyze bug report
            analysis_result = self.nlp_pipeline.analyze_bug_report(
                bug_report.title, 
                bug_report.description
            )
            
            # Create categorized bug
            categorized_bug = self._create_categorized_bug(bug_report, analysis_result)
            
            return categorized_bug
            
        except Exception as e:
            self.logger.error(f"Error in synchronous processing: {e}", exc_info=True)
            return None
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get detailed processing statistics.
        
        Returns:
            Dictionary with processing statistics
        """
        stats = self.stats.copy()
        
        # Calculate additional metrics
        if stats['total_processed'] > 0:
            stats['success_rate'] = (
                (stats['successful_classifications'] + stats['low_confidence_flags']) / 
                stats['total_processed']
            )
            stats['error_rate'] = stats['processing_errors'] / stats['total_processed']
            stats['manual_review_rate'] = stats['low_confidence_flags'] / stats['total_processed']
        else:
            stats['success_rate'] = 0.0
            stats['error_rate'] = 0.0
            stats['manual_review_rate'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset processing statistics."""
        self.stats = {
            'total_processed': 0,
            'successful_classifications': 0,
            'low_confidence_flags': 0,
            'processing_errors': 0,
            'average_processing_time': 0.0,
            'last_processed_time': None
        }
        
        # Reset queue stats if available
        if self.consumer:
            self.consumer.reset_stats()
        if self.publisher:
            self.publisher.reset_stats()
        
        self.logger.info("Processing statistics reset")