"""Assignment accuracy tracking and reporting."""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from smart_bug_triage.database.connection import get_db_session
from smart_bug_triage.models.database import (
    AssignmentAccuracy, Assignment, AssignmentFeedback, Bug, Developer
)
from smart_bug_triage.models.common import BugCategory
from smart_bug_triage.utils.logging import get_logger


@dataclass
class AccuracyReport:
    """Accuracy metrics report."""
    overall_accuracy: float
    category_accuracy: Dict[str, float]
    developer_accuracy: Dict[str, float]
    time_period: str
    total_assignments: int
    feedback_count: int
    avg_resolution_time: float
    reassignment_rate: float


class AccuracyTracker:
    """Tracks and analyzes assignment accuracy metrics."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def record_assignment_accuracy(self, assignment_id: str, predicted_category: BugCategory,
                                 predicted_developer: str, actual_category: Optional[BugCategory] = None,
                                 feedback_rating: Optional[int] = None, 
                                 resolution_time_minutes: Optional[int] = None,
                                 was_reassigned: bool = False) -> None:
        """Record accuracy data for an assignment."""
        try:
            # Calculate accuracy score based on available data
            accuracy_score = self._calculate_accuracy_score(
                predicted_category, actual_category, feedback_rating, was_reassigned
            )
            
            with get_db_session() as session:
                accuracy_record = AssignmentAccuracy(
                    assignment_id=assignment_id,
                    predicted_category=predicted_category,
                    actual_category=actual_category,
                    predicted_developer=predicted_developer,
                    feedback_rating=feedback_rating,
                    resolution_time_minutes=resolution_time_minutes,
                    was_reassigned=was_reassigned,
                    accuracy_score=accuracy_score
                )
                
                session.add(accuracy_record)
                session.commit()
                
                self.logger.debug(f"Recorded accuracy for assignment {assignment_id}: {accuracy_score}")
                
        except Exception as e:
            self.logger.error(f"Failed to record assignment accuracy: {str(e)}")
    
    def _calculate_accuracy_score(self, predicted_category: BugCategory, 
                                actual_category: Optional[BugCategory],
                                feedback_rating: Optional[int], 
                                was_reassigned: bool) -> float:
        """Calculate accuracy score based on available metrics."""
        score = 0.0
        weight_sum = 0.0
        
        # Category accuracy (weight: 0.3)
        if actual_category is not None:
            category_correct = predicted_category == actual_category
            score += 0.3 * (1.0 if category_correct else 0.0)
            weight_sum += 0.3
        
        # Feedback rating (weight: 0.4)
        if feedback_rating is not None:
            # Convert 1-5 rating to 0-1 score
            feedback_score = (feedback_rating - 1) / 4.0
            score += 0.4 * feedback_score
            weight_sum += 0.4
        
        # Reassignment penalty (weight: 0.3)
        reassignment_score = 0.0 if was_reassigned else 1.0
        score += 0.3 * reassignment_score
        weight_sum += 0.3
        
        # Normalize by actual weights used
        return score / weight_sum if weight_sum > 0 else 0.5
    
    def update_accuracy_from_feedback(self, assignment_id: str) -> None:
        """Update accuracy record when feedback is received."""
        try:
            with get_db_session() as session:
                # Get the assignment and its feedback
                assignment_data = session.query(
                    Assignment, AssignmentFeedback, Bug
                ).join(
                    AssignmentFeedback, Assignment.id == AssignmentFeedback.assignment_id
                ).join(
                    Bug, Assignment.bug_id == Bug.id
                ).filter(Assignment.id == assignment_id).first()
                
                if not assignment_data:
                    self.logger.warning(f"No assignment data found for {assignment_id}")
                    return
                
                assignment, feedback, bug = assignment_data
                
                # Check if accuracy record exists
                accuracy_record = session.query(AssignmentAccuracy).filter(
                    AssignmentAccuracy.assignment_id == assignment_id
                ).first()
                
                if accuracy_record:
                    # Update existing record
                    accuracy_record.feedback_rating = feedback.rating
                    accuracy_record.resolution_time_minutes = feedback.resolution_time
                    accuracy_record.actual_category = bug.category
                    accuracy_record.accuracy_score = self._calculate_accuracy_score(
                        accuracy_record.predicted_category,
                        bug.category,
                        feedback.rating,
                        accuracy_record.was_reassigned
                    )
                else:
                    # Create new record
                    self.record_assignment_accuracy(
                        assignment_id=assignment_id,
                        predicted_category=bug.category,  # Use current category as predicted
                        predicted_developer=assignment.developer_id,
                        actual_category=bug.category,
                        feedback_rating=feedback.rating,
                        resolution_time_minutes=feedback.resolution_time,
                        was_reassigned=assignment.status == 'reassigned'
                    )
                
                session.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to update accuracy from feedback: {str(e)}")
    
    def get_accuracy_report(self, days: int = 30) -> AccuracyReport:
        """Generate comprehensive accuracy report."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with get_db_session() as session:
                # Get all accuracy records in the time period
                accuracy_records = session.query(AssignmentAccuracy).filter(
                    AssignmentAccuracy.recorded_at >= cutoff_date
                ).all()
                
                if not accuracy_records:
                    return AccuracyReport(
                        overall_accuracy=0.0,
                        category_accuracy={},
                        developer_accuracy={},
                        time_period=f"Last {days} days",
                        total_assignments=0,
                        feedback_count=0,
                        avg_resolution_time=0.0,
                        reassignment_rate=0.0
                    )
                
                # Calculate overall accuracy
                valid_scores = [r.accuracy_score for r in accuracy_records if r.accuracy_score is not None]
                overall_accuracy = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
                
                # Calculate category accuracy
                category_accuracy = self._calculate_category_accuracy(accuracy_records)
                
                # Calculate developer accuracy
                developer_accuracy = self._calculate_developer_accuracy(accuracy_records)
                
                # Calculate other metrics
                total_assignments = len(accuracy_records)
                feedback_count = len([r for r in accuracy_records if r.feedback_rating is not None])
                
                resolution_times = [r.resolution_time_minutes for r in accuracy_records 
                                  if r.resolution_time_minutes is not None]
                avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0.0
                
                reassignment_count = len([r for r in accuracy_records if r.was_reassigned])
                reassignment_rate = (reassignment_count / total_assignments * 100) if total_assignments > 0 else 0.0
                
                return AccuracyReport(
                    overall_accuracy=overall_accuracy,
                    category_accuracy=category_accuracy,
                    developer_accuracy=developer_accuracy,
                    time_period=f"Last {days} days",
                    total_assignments=total_assignments,
                    feedback_count=feedback_count,
                    avg_resolution_time=avg_resolution_time,
                    reassignment_rate=reassignment_rate
                )
                
        except Exception as e:
            self.logger.error(f"Failed to generate accuracy report: {str(e)}")
            return AccuracyReport(
                overall_accuracy=0.0,
                category_accuracy={},
                developer_accuracy={},
                time_period=f"Last {days} days (ERROR)",
                total_assignments=0,
                feedback_count=0,
                avg_resolution_time=0.0,
                reassignment_rate=0.0
            )
    
    def _calculate_category_accuracy(self, records: List[AssignmentAccuracy]) -> Dict[str, float]:
        """Calculate accuracy by bug category."""
        category_scores = {}
        category_counts = {}
        
        for record in records:
            if record.predicted_category and record.accuracy_score is not None:
                category = record.predicted_category.value
                if category not in category_scores:
                    category_scores[category] = 0.0
                    category_counts[category] = 0
                
                category_scores[category] += record.accuracy_score
                category_counts[category] += 1
        
        return {
            category: category_scores[category] / category_counts[category]
            for category in category_scores
        }
    
    def _calculate_developer_accuracy(self, records: List[AssignmentAccuracy]) -> Dict[str, float]:
        """Calculate accuracy by developer."""
        developer_scores = {}
        developer_counts = {}
        
        for record in records:
            if record.predicted_developer and record.accuracy_score is not None:
                developer = record.predicted_developer
                if developer not in developer_scores:
                    developer_scores[developer] = 0.0
                    developer_counts[developer] = 0
                
                developer_scores[developer] += record.accuracy_score
                developer_counts[developer] += 1
        
        return {
            developer: developer_scores[developer] / developer_counts[developer]
            for developer in developer_scores
        }
    
    def get_accuracy_trends(self, days: int = 90) -> Dict[str, List[Tuple[str, float]]]:
        """Get accuracy trends over time."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with get_db_session() as session:
                # Get daily accuracy averages
                daily_accuracy = session.query(
                    func.date(AssignmentAccuracy.recorded_at).label('date'),
                    func.avg(AssignmentAccuracy.accuracy_score).label('avg_accuracy')
                ).filter(
                    and_(
                        AssignmentAccuracy.recorded_at >= cutoff_date,
                        AssignmentAccuracy.accuracy_score.isnot(None)
                    )
                ).group_by(
                    func.date(AssignmentAccuracy.recorded_at)
                ).order_by('date').all()
                
                # Get category trends
                category_trends = {}
                for category in BugCategory:
                    category_daily = session.query(
                        func.date(AssignmentAccuracy.recorded_at).label('date'),
                        func.avg(AssignmentAccuracy.accuracy_score).label('avg_accuracy')
                    ).filter(
                        and_(
                            AssignmentAccuracy.recorded_at >= cutoff_date,
                            AssignmentAccuracy.predicted_category == category,
                            AssignmentAccuracy.accuracy_score.isnot(None)
                        )
                    ).group_by(
                        func.date(AssignmentAccuracy.recorded_at)
                    ).order_by('date').all()
                    
                    category_trends[category.value] = [
                        (str(row.date), float(row.avg_accuracy))
                        for row in category_daily
                    ]
                
                return {
                    'overall': [(str(row.date), float(row.avg_accuracy)) for row in daily_accuracy],
                    **category_trends
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get accuracy trends: {str(e)}")
            return {'overall': [], 'error': str(e)}
    
    def get_low_performing_areas(self, threshold: float = 0.7) -> Dict[str, List[str]]:
        """Identify categories and developers with accuracy below threshold."""
        try:
            report = self.get_accuracy_report(30)  # Last 30 days
            
            low_categories = [
                category for category, accuracy in report.category_accuracy.items()
                if accuracy < threshold
            ]
            
            low_developers = [
                developer for developer, accuracy in report.developer_accuracy.items()
                if accuracy < threshold
            ]
            
            return {
                'categories': low_categories,
                'developers': low_developers,
                'threshold': threshold
            }
            
        except Exception as e:
            self.logger.error(f"Failed to identify low performing areas: {str(e)}")
            return {'categories': [], 'developers': [], 'threshold': threshold, 'error': str(e)}