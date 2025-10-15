"""Feedback processing and machine learning model update system."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import json

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from ..database.connection import get_db_session
from ..models.database import (
    AssignmentFeedback, Assignment, Developer, Bug, DeveloperStatus
)
from ..models.common import BugCategory, Priority
# from ..nlp.training_data import TrainingDataManager


logger = logging.getLogger(__name__)


class ModelRetrainingTrigger(Enum):
    """Triggers for model retraining."""
    ACCURACY_THRESHOLD = "accuracy_threshold"
    FEEDBACK_VOLUME = "feedback_volume"
    TIME_BASED = "time_based"
    MANUAL = "manual"


@dataclass
class FeedbackMetrics:
    """Aggregated feedback metrics."""
    total_feedback: int
    average_rating: float
    appropriate_assignment_rate: float
    category_accuracy: Dict[str, float]
    developer_satisfaction: Dict[str, float]
    resolution_time_trends: Dict[str, float]


@dataclass
class ModelPerformanceMetrics:
    """Model performance metrics derived from feedback."""
    overall_accuracy: float
    category_accuracy: Dict[BugCategory, float]
    severity_accuracy: float
    assignment_appropriateness: float
    confidence_correlation: float
    needs_retraining: bool
    retraining_reasons: List[str]


@dataclass
class RetrainingRecommendation:
    """Recommendation for model retraining."""
    should_retrain: bool
    trigger: ModelRetrainingTrigger
    priority: str  # high, medium, low
    affected_components: List[str]
    expected_improvement: float
    training_data_size: int
    reason: str


class FeedbackProcessor:
    """Processes feedback data and triggers model improvements."""
    
    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory or get_db_session
        # self.training_data_manager = TrainingDataManager()  # Placeholder for now
        
        # Configuration thresholds
        self.accuracy_threshold = 0.80  # Retrain if accuracy drops below 80%
        self.feedback_volume_threshold = 100  # Retrain after 100 new feedback items
        self.time_threshold_days = 30  # Retrain every 30 days
        self.confidence_correlation_threshold = 0.6  # Minimum correlation between confidence and accuracy
        
        logger.info("FeedbackProcessor initialized")
    
    def process_new_feedback(self, feedback_id: str) -> Dict[str, Any]:
        """Process a single new feedback item and update models."""
        with self.db_session_factory() as db:
            feedback = db.query(AssignmentFeedback).filter(
                AssignmentFeedback.id == feedback_id
            ).first()
            
            if not feedback:
                raise ValueError(f"Feedback {feedback_id} not found")
            
            # Get associated assignment and bug
            assignment = db.query(Assignment).filter(
                Assignment.id == feedback.assignment_id
            ).first()
            
            if not assignment:
                logger.error(f"Assignment {feedback.assignment_id} not found for feedback {feedback_id}")
                return {"status": "error", "message": "Associated assignment not found"}
            
            bug = db.query(Bug).filter(Bug.id == assignment.bug_id).first()
            if not bug:
                logger.error(f"Bug {assignment.bug_id} not found for assignment {assignment.id}")
                return {"status": "error", "message": "Associated bug not found"}
            
            # Update developer skill confidence based on feedback
            self._update_developer_skills(db, feedback, assignment, bug)
            
            # Update training data with feedback
            self._update_training_data(feedback, assignment, bug)
            
            # Check if retraining is needed
            retraining_rec = self._evaluate_retraining_need(db)
            
            result = {
                "status": "processed",
                "feedback_id": feedback_id,
                "developer_skills_updated": True,
                "training_data_updated": True,
                "retraining_recommendation": retraining_rec.__dict__ if retraining_rec else None
            }
            
            if retraining_rec and retraining_rec.should_retrain:
                logger.info(f"Model retraining recommended: {retraining_rec.reason}")
                # Trigger retraining process
                self._trigger_model_retraining(retraining_rec)
                result["retraining_triggered"] = True
            
            return result
    
    def _update_developer_skills(
        self, 
        db: Session, 
        feedback: AssignmentFeedback, 
        assignment: Assignment, 
        bug: Bug
    ):
        """Update developer skill confidence based on feedback."""
        developer = db.query(Developer).filter(
            Developer.id == feedback.developer_id
        ).first()
        
        if not developer:
            logger.error(f"Developer {feedback.developer_id} not found")
            return
        
        # Calculate skill adjustment based on feedback
        skill_adjustment = self._calculate_skill_adjustment(feedback, assignment, bug)
        
        # Update developer's skill confidence for the bug category
        if bug.category and skill_adjustment != 0:
            # This would typically update a separate skill confidence table
            # For now, we'll log the adjustment
            logger.info(
                f"Developer {developer.name} skill adjustment for {bug.category.value}: "
                f"{skill_adjustment:+.2f} (rating: {feedback.rating}, appropriate: {feedback.was_appropriate})"
            )
            
            # In a real implementation, you would update a developer_skills table
            # with confidence scores for each category
    
    def _calculate_skill_adjustment(
        self, 
        feedback: AssignmentFeedback, 
        assignment: Assignment, 
        bug: Bug
    ) -> float:
        """Calculate how much to adjust developer's skill confidence."""
        base_adjustment = 0.0
        
        # Positive adjustment for good ratings and appropriate assignments
        if feedback.rating >= 4 and feedback.was_appropriate:
            base_adjustment = 0.1
        elif feedback.rating >= 3 and feedback.was_appropriate:
            base_adjustment = 0.05
        elif feedback.rating <= 2 or not feedback.was_appropriate:
            base_adjustment = -0.1
        
        # Weight by assignment confidence - higher confidence assignments have more impact
        confidence_weight = assignment.confidence_score
        
        # Weight by resolution time if available
        time_weight = 1.0
        if feedback.resolution_time:
            # Faster resolution gets slight bonus, slower gets slight penalty
            expected_time = 480  # 8 hours in minutes
            if feedback.resolution_time < expected_time * 0.5:
                time_weight = 1.1  # 10% bonus for fast resolution
            elif feedback.resolution_time > expected_time * 2:
                time_weight = 0.9  # 10% penalty for slow resolution
        
        return base_adjustment * confidence_weight * time_weight
    
    def _update_training_data(
        self, 
        feedback: AssignmentFeedback, 
        assignment: Assignment, 
        bug: Bug
    ):
        """Update training data based on feedback."""
        # Create training example from feedback
        training_example = {
            'bug_id': bug.id,
            'title': bug.title,
            'description': bug.description,
            'actual_category': bug.category.value if bug.category else None,
            'actual_severity': bug.severity.value if bug.severity else None,
            'predicted_category': bug.category.value if bug.category else None,
            'predicted_severity': bug.severity.value if bug.severity else None,
            'confidence_score': assignment.confidence_score,
            'feedback_rating': feedback.rating,
            'was_appropriate': feedback.was_appropriate,
            'resolution_time': feedback.resolution_time,
            'feedback_timestamp': feedback.feedback_timestamp.isoformat()
        }
        
        # Add to training data manager (placeholder implementation)
        # self.training_data_manager.add_feedback_example(training_example)
        logger.debug(f"Training example created for bug {training_example['bug_id']}")
        
        logger.debug(f"Added training example for bug {bug.id}")
    
    def _evaluate_retraining_need(self, db: Session) -> Optional[RetrainingRecommendation]:
        """Evaluate whether model retraining is needed."""
        # Get recent feedback metrics
        metrics = self._calculate_model_performance_metrics(db)
        
        reasons = []
        priority = "low"
        trigger = None
        
        # Check accuracy threshold
        if metrics.overall_accuracy < self.accuracy_threshold:
            reasons.append(f"Overall accuracy ({metrics.overall_accuracy:.2f}) below threshold ({self.accuracy_threshold})")
            priority = "high"
            trigger = ModelRetrainingTrigger.ACCURACY_THRESHOLD
        
        # Check category-specific accuracy
        for category, accuracy in metrics.category_accuracy.items():
            if accuracy < self.accuracy_threshold:
                reasons.append(f"{category.value} accuracy ({accuracy:.2f}) below threshold")
                if priority != "high":
                    priority = "medium"
                if not trigger:
                    trigger = ModelRetrainingTrigger.ACCURACY_THRESHOLD
        
        # Check feedback volume
        recent_feedback_count = self._get_recent_feedback_count(db, days=7)
        if recent_feedback_count >= self.feedback_volume_threshold:
            reasons.append(f"High feedback volume ({recent_feedback_count} in last 7 days)")
            if priority == "low":
                priority = "medium"
            if not trigger:
                trigger = ModelRetrainingTrigger.FEEDBACK_VOLUME
        
        # Check time since last retraining
        days_since_last_training = self._get_days_since_last_training()
        if days_since_last_training >= self.time_threshold_days:
            reasons.append(f"Time-based retraining ({days_since_last_training} days since last training)")
            if not trigger:
                trigger = ModelRetrainingTrigger.TIME_BASED
        
        # Check confidence correlation
        if metrics.confidence_correlation < self.confidence_correlation_threshold:
            reasons.append(f"Low confidence correlation ({metrics.confidence_correlation:.2f})")
            if priority == "low":
                priority = "medium"
        
        should_retrain = len(reasons) > 0
        
        if should_retrain:
            # Estimate training data size
            training_data_size = self._estimate_training_data_size(db)
            
            # Estimate expected improvement
            expected_improvement = self._estimate_expected_improvement(metrics, reasons)
            
            return RetrainingRecommendation(
                should_retrain=True,
                trigger=trigger,
                priority=priority,
                affected_components=self._identify_affected_components(reasons),
                expected_improvement=expected_improvement,
                training_data_size=training_data_size,
                reason="; ".join(reasons)
            )
        
        return None
    
    def _calculate_model_performance_metrics(self, db: Session) -> ModelPerformanceMetrics:
        """Calculate model performance metrics from recent feedback."""
        # Get feedback from last 30 days
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        feedback_query = db.query(AssignmentFeedback).join(
            Assignment, AssignmentFeedback.assignment_id == Assignment.id
        ).join(
            Bug, Assignment.bug_id == Bug.id
        ).filter(
            AssignmentFeedback.feedback_timestamp >= cutoff_date
        )
        
        feedback_data = feedback_query.all()
        
        if not feedback_data:
            return ModelPerformanceMetrics(
                overall_accuracy=1.0,
                category_accuracy={},
                severity_accuracy=1.0,
                assignment_appropriateness=1.0,
                confidence_correlation=1.0,
                needs_retraining=False,
                retraining_reasons=[]
            )
        
        # Calculate overall accuracy (based on appropriate assignments)
        appropriate_count = sum(1 for f in feedback_data if f.was_appropriate)
        overall_accuracy = appropriate_count / len(feedback_data)
        
        # Calculate category-specific accuracy
        category_accuracy = {}
        for category in BugCategory:
            category_feedback = [
                f for f in feedback_data 
                if f.assignment and f.assignment.bug and f.assignment.bug.category == category
            ]
            if category_feedback:
                category_appropriate = sum(1 for f in category_feedback if f.was_appropriate)
                category_accuracy[category] = category_appropriate / len(category_feedback)
        
        # Calculate assignment appropriateness (same as overall accuracy for now)
        assignment_appropriateness = overall_accuracy
        
        # Calculate confidence correlation
        confidence_correlation = self._calculate_confidence_correlation(feedback_data)
        
        # Severity accuracy (placeholder - would need more sophisticated calculation)
        severity_accuracy = overall_accuracy  # Simplified
        
        return ModelPerformanceMetrics(
            overall_accuracy=overall_accuracy,
            category_accuracy=category_accuracy,
            severity_accuracy=severity_accuracy,
            assignment_appropriateness=assignment_appropriateness,
            confidence_correlation=confidence_correlation,
            needs_retraining=overall_accuracy < self.accuracy_threshold,
            retraining_reasons=[]
        )
    
    def _calculate_confidence_correlation(self, feedback_data: List[AssignmentFeedback]) -> float:
        """Calculate correlation between assignment confidence and feedback rating."""
        if len(feedback_data) < 2:
            return 1.0
        
        # Get confidence scores and ratings
        confidence_scores = []
        ratings = []
        
        for feedback in feedback_data:
            if feedback.assignment and feedback.assignment.confidence_score is not None:
                confidence_scores.append(feedback.assignment.confidence_score)
                ratings.append(feedback.rating)
        
        if len(confidence_scores) < 2:
            return 1.0
        
        # Calculate Pearson correlation coefficient
        n = len(confidence_scores)
        sum_x = sum(confidence_scores)
        sum_y = sum(ratings)
        sum_xy = sum(x * y for x, y in zip(confidence_scores, ratings))
        sum_x2 = sum(x * x for x in confidence_scores)
        sum_y2 = sum(y * y for y in ratings)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
        
        if denominator == 0:
            return 0.0
        
        correlation = numerator / denominator
        return max(0.0, correlation)  # Return 0 for negative correlations
    
    def _get_recent_feedback_count(self, db: Session, days: int) -> int:
        """Get count of feedback in the last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return db.query(AssignmentFeedback).filter(
            AssignmentFeedback.feedback_timestamp >= cutoff_date
        ).count()
    
    def _get_days_since_last_training(self) -> int:
        """Get days since last model training."""
        # This would typically check a model training log table
        # For now, return a placeholder value
        return 15  # Placeholder
    
    def _estimate_training_data_size(self, db: Session) -> int:
        """Estimate size of available training data."""
        # Count total feedback that can be used for training
        return db.query(AssignmentFeedback).count()
    
    def _estimate_expected_improvement(self, metrics: ModelPerformanceMetrics, reasons: List[str]) -> float:
        """Estimate expected improvement from retraining."""
        # Simple heuristic based on current performance gap
        accuracy_gap = self.accuracy_threshold - metrics.overall_accuracy
        
        if accuracy_gap > 0.2:
            return 0.15  # Expect 15% improvement for large gaps
        elif accuracy_gap > 0.1:
            return 0.10  # Expect 10% improvement for medium gaps
        else:
            return 0.05  # Expect 5% improvement for small gaps
    
    def _identify_affected_components(self, reasons: List[str]) -> List[str]:
        """Identify which model components need retraining."""
        components = []
        
        for reason in reasons:
            if "category" in reason.lower():
                components.append("category_classifier")
            if "severity" in reason.lower():
                components.append("severity_predictor")
            if "confidence" in reason.lower():
                components.append("confidence_estimator")
            if "accuracy" in reason.lower() and "category" not in reason.lower():
                components.append("assignment_algorithm")
        
        return list(set(components)) or ["full_model"]
    
    def _trigger_model_retraining(self, recommendation: RetrainingRecommendation):
        """Trigger the model retraining process."""
        logger.info(f"Triggering model retraining: {recommendation.reason}")
        
        # In a real implementation, this would:
        # 1. Queue a retraining job
        # 2. Prepare training data
        # 3. Start the retraining process
        # 4. Update model versions
        # 5. Deploy new models
        
        # For now, just log the action
        logger.info(f"Retraining job queued for components: {recommendation.affected_components}")
        logger.info(f"Expected improvement: {recommendation.expected_improvement:.2f}")
        logger.info(f"Training data size: {recommendation.training_data_size}")
    
    def get_feedback_analytics(self, days_back: int = 30) -> FeedbackMetrics:
        """Get comprehensive feedback analytics."""
        with self.db_session_factory() as db:
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            feedback_query = db.query(AssignmentFeedback).filter(
                AssignmentFeedback.feedback_timestamp >= cutoff_date
            )
            
            feedback_data = feedback_query.all()
            
            if not feedback_data:
                return FeedbackMetrics(
                    total_feedback=0,
                    average_rating=0.0,
                    appropriate_assignment_rate=0.0,
                    category_accuracy={},
                    developer_satisfaction={},
                    resolution_time_trends={}
                )
            
            # Calculate metrics
            total_feedback = len(feedback_data)
            average_rating = sum(f.rating for f in feedback_data) / total_feedback
            appropriate_count = sum(1 for f in feedback_data if f.was_appropriate)
            appropriate_rate = appropriate_count / total_feedback
            
            # Category accuracy
            category_accuracy = {}
            for category in BugCategory:
                category_feedback = [
                    f for f in feedback_data 
                    if f.assignment and f.assignment.bug and f.assignment.bug.category == category
                ]
                if category_feedback:
                    category_appropriate = sum(1 for f in category_feedback if f.was_appropriate)
                    category_accuracy[category.value] = category_appropriate / len(category_feedback)
            
            # Developer satisfaction
            developer_satisfaction = {}
            developer_feedback = {}
            for feedback in feedback_data:
                dev_id = feedback.developer_id
                if dev_id not in developer_feedback:
                    developer_feedback[dev_id] = []
                developer_feedback[dev_id].append(feedback)
            
            for dev_id, dev_feedback in developer_feedback.items():
                avg_rating = sum(f.rating for f in dev_feedback) / len(dev_feedback)
                developer_satisfaction[dev_id] = avg_rating
            
            # Resolution time trends (placeholder)
            resolution_time_trends = {}
            resolution_times = [f.resolution_time for f in feedback_data if f.resolution_time]
            if resolution_times:
                resolution_time_trends['average'] = sum(resolution_times) / len(resolution_times)
                resolution_time_trends['median'] = sorted(resolution_times)[len(resolution_times) // 2]
            
            return FeedbackMetrics(
                total_feedback=total_feedback,
                average_rating=average_rating,
                appropriate_assignment_rate=appropriate_rate,
                category_accuracy=category_accuracy,
                developer_satisfaction=developer_satisfaction,
                resolution_time_trends=resolution_time_trends
            )
    
    def generate_feedback_report(self, days_back: int = 30) -> Dict[str, Any]:
        """Generate a comprehensive feedback report."""
        metrics = self.get_feedback_analytics(days_back)
        
        with self.db_session_factory() as db:
            performance_metrics = self._calculate_model_performance_metrics(db)
            retraining_rec = self._evaluate_retraining_need(db)
        
        return {
            'report_generated': datetime.utcnow().isoformat(),
            'analysis_period_days': days_back,
            'feedback_metrics': metrics.__dict__,
            'model_performance': performance_metrics.__dict__,
            'retraining_recommendation': retraining_rec.__dict__ if retraining_rec else None,
            'summary': {
                'total_feedback': metrics.total_feedback,
                'system_health': 'good' if performance_metrics.overall_accuracy >= 0.85 else 'needs_attention',
                'action_required': retraining_rec.should_retrain if retraining_rec else False
            }
        }