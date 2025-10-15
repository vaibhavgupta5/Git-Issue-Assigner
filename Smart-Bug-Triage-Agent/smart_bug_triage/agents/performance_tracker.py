"""Performance metrics calculation and tracking for developers."""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, median
from sqlalchemy.orm import Session

from ..models.database import Assignment, AssignmentFeedback, Developer, WorkloadSnapshot
from ..models.common import BugCategory, Priority


@dataclass
class PerformanceMetrics:
    """Developer performance metrics."""
    developer_id: str
    total_assignments: int
    completed_assignments: int
    average_resolution_time: float  # hours
    median_resolution_time: float  # hours
    success_rate: float  # percentage of assignments completed successfully
    feedback_score: float  # average feedback rating (1-5)
    category_performance: Dict[BugCategory, float]  # success rate by category
    priority_performance: Dict[Priority, float]  # success rate by priority
    workload_efficiency: float  # assignments completed per unit of capacity
    recent_trend: str  # "improving", "stable", "declining"
    last_calculated: datetime


@dataclass
class SkillConfidence:
    """Skill confidence scoring for a developer."""
    developer_id: str
    skill_scores: Dict[str, float]  # skill -> confidence score (0.0-1.0)
    category_confidence: Dict[BugCategory, float]  # category -> confidence (0.0-1.0)
    learning_velocity: Dict[str, float]  # skill -> rate of improvement
    last_updated: datetime


class PerformanceTracker:
    """Tracks and calculates developer performance metrics."""
    
    def __init__(self, db_session: Session):
        """Initialize performance tracker.
        
        Args:
            db_session: Database session
        """
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)
    
    def calculate_performance_metrics(
        self,
        developer_id: str,
        lookback_days: int = 90
    ) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics for a developer.
        
        Args:
            developer_id: Developer ID
            lookback_days: Number of days to look back for calculations
            
        Returns:
            Performance metrics
        """
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        # Get assignments within the lookback period
        assignments = self.db_session.query(Assignment).filter(
            Assignment.developer_id == developer_id,
            Assignment.assigned_at >= cutoff_date
        ).all()
        
        if not assignments:
            return self._empty_metrics(developer_id)
        
        # Calculate basic metrics
        total_assignments = len(assignments)
        completed_assignments = len([a for a in assignments if a.status == 'completed'])
        
        # Calculate resolution times
        resolution_times = []
        for assignment in assignments:
            if assignment.completed_at and assignment.assigned_at:
                resolution_hours = (assignment.completed_at - assignment.assigned_at).total_seconds() / 3600
                resolution_times.append(resolution_hours)
        
        avg_resolution_time = mean(resolution_times) if resolution_times else 0.0
        median_resolution_time = median(resolution_times) if resolution_times else 0.0
        
        # Calculate success rate
        success_rate = (completed_assignments / total_assignments) * 100 if total_assignments > 0 else 0.0
        
        # Calculate feedback score
        feedback_score = self._calculate_feedback_score(developer_id, cutoff_date)
        
        # Calculate category and priority performance
        category_performance = self._calculate_category_performance(assignments)
        priority_performance = self._calculate_priority_performance(assignments)
        
        # Calculate workload efficiency
        workload_efficiency = self._calculate_workload_efficiency(developer_id, lookback_days)
        
        # Determine recent trend
        recent_trend = self._calculate_trend(developer_id, lookback_days)
        
        return PerformanceMetrics(
            developer_id=developer_id,
            total_assignments=total_assignments,
            completed_assignments=completed_assignments,
            average_resolution_time=avg_resolution_time,
            median_resolution_time=median_resolution_time,
            success_rate=success_rate,
            feedback_score=feedback_score,
            category_performance=category_performance,
            priority_performance=priority_performance,
            workload_efficiency=workload_efficiency,
            recent_trend=recent_trend,
            last_calculated=datetime.now()
        )
    
    def calculate_skill_confidence(
        self,
        developer_id: str,
        lookback_days: int = 180
    ) -> SkillConfidence:
        """Calculate skill confidence scores based on assignment outcomes.
        
        Args:
            developer_id: Developer ID
            lookback_days: Number of days to look back for calculations
            
        Returns:
            Skill confidence scores
        """
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        # Get developer profile
        developer = self.db_session.query(Developer).filter_by(id=developer_id).first()
        if not developer:
            return self._empty_skill_confidence(developer_id)
        
        # Get assignments with feedback
        assignments_with_feedback = self.db_session.query(Assignment, AssignmentFeedback).join(
            AssignmentFeedback, Assignment.id == AssignmentFeedback.assignment_id
        ).filter(
            Assignment.developer_id == developer_id,
            Assignment.assigned_at >= cutoff_date
        ).all()
        
        # Initialize skill scores with base confidence
        skill_scores = {skill: 0.5 for skill in developer.skills}  # Start at 50%
        category_confidence = {category: 0.5 for category in BugCategory}
        
        # Calculate confidence based on assignment outcomes
        for assignment, feedback in assignments_with_feedback:
            # Get bug category from assignment
            bug = assignment.bug
            if not bug or not bug.category:
                continue
            
            category = bug.category
            
            # Calculate success factor based on feedback
            success_factor = self._calculate_success_factor(feedback)
            
            # Update category confidence
            current_confidence = category_confidence.get(category, 0.5)
            # Use exponential moving average with learning rate
            learning_rate = 0.1
            category_confidence[category] = current_confidence + learning_rate * (success_factor - current_confidence)
            
            # Update skill scores based on category mapping
            relevant_skills = self._map_category_to_skills(category, developer.skills)
            for skill in relevant_skills:
                current_skill_score = skill_scores.get(skill, 0.5)
                skill_scores[skill] = current_skill_score + learning_rate * (success_factor - current_skill_score)
        
        # Ensure scores are within bounds
        skill_scores = {skill: max(0.0, min(1.0, score)) for skill, score in skill_scores.items()}
        category_confidence = {cat: max(0.0, min(1.0, score)) for cat, score in category_confidence.items()}
        
        # Calculate learning velocity (rate of improvement)
        learning_velocity = self._calculate_learning_velocity(developer_id, skill_scores, lookback_days)
        
        return SkillConfidence(
            developer_id=developer_id,
            skill_scores=skill_scores,
            category_confidence=category_confidence,
            learning_velocity=learning_velocity,
            last_updated=datetime.now()
        )
    
    def update_performance_from_feedback(
        self,
        developer_id: str,
        assignment_id: str,
        feedback: AssignmentFeedback
    ) -> None:
        """Update performance metrics based on new feedback.
        
        Args:
            developer_id: Developer ID
            assignment_id: Assignment ID
            feedback: Assignment feedback
        """
        try:
            # Get the assignment
            assignment = self.db_session.query(Assignment).filter_by(id=assignment_id).first()
            if not assignment:
                self.logger.warning(f"Assignment {assignment_id} not found")
                return
            
            # Update assignment status if completed
            if feedback.resolution_time and assignment.status == 'active':
                assignment.status = 'completed'
                assignment.completed_at = feedback.feedback_timestamp
                self.db_session.commit()
            
            # Recalculate skill confidence with new feedback
            skill_confidence = self.calculate_skill_confidence(developer_id)
            
            # Log the update
            self.logger.info(
                f"Updated performance metrics for developer {developer_id} "
                f"based on feedback for assignment {assignment_id}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to update performance from feedback: {e}")
            self.db_session.rollback()
    
    def get_performance_trend(
        self,
        developer_id: str,
        metric: str = "success_rate",
        days: int = 30
    ) -> List[Tuple[datetime, float]]:
        """Get performance trend over time.
        
        Args:
            developer_id: Developer ID
            metric: Metric to track ("success_rate", "resolution_time", "feedback_score")
            days: Number of days to analyze
            
        Returns:
            List of (date, value) tuples
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Calculate metrics for each week
        trend_data = []
        current_date = start_date
        
        while current_date < end_date:
            week_end = min(current_date + timedelta(days=7), end_date)
            
            # Get assignments for this week
            week_assignments = self.db_session.query(Assignment).filter(
                Assignment.developer_id == developer_id,
                Assignment.assigned_at >= current_date,
                Assignment.assigned_at < week_end
            ).all()
            
            if week_assignments:
                if metric == "success_rate":
                    completed = len([a for a in week_assignments if a.status == 'completed'])
                    value = (completed / len(week_assignments)) * 100
                elif metric == "resolution_time":
                    resolution_times = []
                    for assignment in week_assignments:
                        if assignment.completed_at and assignment.assigned_at:
                            hours = (assignment.completed_at - assignment.assigned_at).total_seconds() / 3600
                            resolution_times.append(hours)
                    value = mean(resolution_times) if resolution_times else 0.0
                elif metric == "feedback_score":
                    value = self._calculate_feedback_score(developer_id, current_date, week_end)
                else:
                    value = 0.0
                
                trend_data.append((current_date, value))
            
            current_date = week_end
        
        return trend_data
    
    def _empty_metrics(self, developer_id: str) -> PerformanceMetrics:
        """Return empty performance metrics."""
        return PerformanceMetrics(
            developer_id=developer_id,
            total_assignments=0,
            completed_assignments=0,
            average_resolution_time=0.0,
            median_resolution_time=0.0,
            success_rate=0.0,
            feedback_score=0.0,
            category_performance={},
            priority_performance={},
            workload_efficiency=0.0,
            recent_trend="stable",
            last_calculated=datetime.now()
        )
    
    def _empty_skill_confidence(self, developer_id: str) -> SkillConfidence:
        """Return empty skill confidence."""
        return SkillConfidence(
            developer_id=developer_id,
            skill_scores={},
            category_confidence={},
            learning_velocity={},
            last_updated=datetime.now()
        )
    
    def _calculate_feedback_score(
        self,
        developer_id: str,
        start_date: datetime,
        end_date: Optional[datetime] = None
    ) -> float:
        """Calculate average feedback score for a developer."""
        query = self.db_session.query(AssignmentFeedback).join(Assignment).filter(
            Assignment.developer_id == developer_id,
            AssignmentFeedback.feedback_timestamp >= start_date
        )
        
        if end_date:
            query = query.filter(AssignmentFeedback.feedback_timestamp < end_date)
        
        feedback_records = query.all()
        
        if not feedback_records:
            return 0.0
        
        ratings = [f.rating for f in feedback_records]
        return mean(ratings)
    
    def _calculate_category_performance(self, assignments: List[Assignment]) -> Dict[BugCategory, float]:
        """Calculate success rate by bug category."""
        category_stats = {}
        
        for assignment in assignments:
            if not assignment.bug or not assignment.bug.category:
                continue
            
            category = assignment.bug.category
            if category not in category_stats:
                category_stats[category] = {"total": 0, "completed": 0}
            
            category_stats[category]["total"] += 1
            if assignment.status == 'completed':
                category_stats[category]["completed"] += 1
        
        # Calculate success rates
        category_performance = {}
        for category, stats in category_stats.items():
            if stats["total"] > 0:
                category_performance[category] = (stats["completed"] / stats["total"]) * 100
        
        return category_performance
    
    def _calculate_priority_performance(self, assignments: List[Assignment]) -> Dict[Priority, float]:
        """Calculate success rate by bug priority."""
        priority_stats = {}
        
        for assignment in assignments:
            if not assignment.bug or not assignment.bug.severity:
                continue
            
            priority = assignment.bug.severity
            if priority not in priority_stats:
                priority_stats[priority] = {"total": 0, "completed": 0}
            
            priority_stats[priority]["total"] += 1
            if assignment.status == 'completed':
                priority_stats[priority]["completed"] += 1
        
        # Calculate success rates
        priority_performance = {}
        for priority, stats in priority_stats.items():
            if stats["total"] > 0:
                priority_performance[priority] = (stats["completed"] / stats["total"]) * 100
        
        return priority_performance
    
    def _calculate_workload_efficiency(self, developer_id: str, lookback_days: int) -> float:
        """Calculate workload efficiency (assignments completed per unit of capacity)."""
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        # Get completed assignments
        completed_assignments = self.db_session.query(Assignment).filter(
            Assignment.developer_id == developer_id,
            Assignment.assigned_at >= cutoff_date,
            Assignment.status == 'completed'
        ).count()
        
        # Get average workload snapshots
        workload_snapshots = self.db_session.query(WorkloadSnapshot).filter(
            WorkloadSnapshot.developer_id == developer_id,
            WorkloadSnapshot.snapshot_time >= cutoff_date
        ).all()
        
        if not workload_snapshots:
            return 0.0
        
        avg_workload = mean([snapshot.workload_score for snapshot in workload_snapshots])
        
        # Calculate efficiency (completed assignments per unit of average workload)
        if avg_workload > 0:
            return completed_assignments / avg_workload
        else:
            return 0.0
    
    def _calculate_trend(self, developer_id: str, lookback_days: int) -> str:
        """Calculate recent performance trend."""
        # Compare recent performance (last 30 days) with previous period
        recent_period = 30
        previous_period = lookback_days - recent_period
        
        if previous_period <= 0:
            return "stable"
        
        # Calculate recent metrics
        recent_cutoff = datetime.now() - timedelta(days=recent_period)
        recent_assignments = self.db_session.query(Assignment).filter(
            Assignment.developer_id == developer_id,
            Assignment.assigned_at >= recent_cutoff
        ).all()
        
        # Calculate previous metrics
        previous_cutoff = datetime.now() - timedelta(days=lookback_days)
        previous_end = recent_cutoff
        previous_assignments = self.db_session.query(Assignment).filter(
            Assignment.developer_id == developer_id,
            Assignment.assigned_at >= previous_cutoff,
            Assignment.assigned_at < previous_end
        ).all()
        
        if not recent_assignments or not previous_assignments:
            return "stable"
        
        # Compare success rates
        recent_success_rate = len([a for a in recent_assignments if a.status == 'completed']) / len(recent_assignments)
        previous_success_rate = len([a for a in previous_assignments if a.status == 'completed']) / len(previous_assignments)
        
        improvement = recent_success_rate - previous_success_rate
        
        if improvement > 0.1:  # 10% improvement
            return "improving"
        elif improvement < -0.1:  # 10% decline
            return "declining"
        else:
            return "stable"
    
    def _calculate_success_factor(self, feedback: AssignmentFeedback) -> float:
        """Calculate success factor from feedback (0.0 to 1.0)."""
        # Combine rating and appropriateness
        rating_factor = (feedback.rating - 1) / 4  # Normalize 1-5 to 0-1
        appropriateness_factor = 1.0 if feedback.was_appropriate else 0.0
        
        # Weight the factors
        return 0.7 * rating_factor + 0.3 * appropriateness_factor
    
    def _map_category_to_skills(self, category: BugCategory, developer_skills: List[str]) -> List[str]:
        """Map bug category to relevant developer skills."""
        category_skill_mapping = {
            BugCategory.FRONTEND: ["javascript", "react", "vue", "angular", "html", "css", "typescript"],
            BugCategory.BACKEND: ["python", "java", "node.js", "go", "rust", "c++", "c#"],
            BugCategory.DATABASE: ["sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch"],
            BugCategory.API: ["rest", "graphql", "api", "microservices", "swagger"],
            BugCategory.MOBILE: ["ios", "android", "react-native", "flutter", "swift", "kotlin"],
            BugCategory.SECURITY: ["security", "authentication", "authorization", "encryption", "oauth"],
            BugCategory.PERFORMANCE: ["optimization", "caching", "performance", "profiling"]
        }
        
        relevant_category_skills = category_skill_mapping.get(category, [])
        
        # Find intersection with developer skills (case-insensitive)
        developer_skills_lower = [skill.lower() for skill in developer_skills]
        relevant_skills = []
        
        for skill in developer_skills:
            skill_lower = skill.lower()
            if any(cat_skill in skill_lower for cat_skill in relevant_category_skills):
                relevant_skills.append(skill)
        
        return relevant_skills if relevant_skills else developer_skills[:3]  # Fallback to first 3 skills
    
    def _calculate_learning_velocity(
        self,
        developer_id: str,
        current_skill_scores: Dict[str, float],
        lookback_days: int
    ) -> Dict[str, float]:
        """Calculate learning velocity for each skill."""
        # This would ideally compare with historical skill scores
        # For now, return zero velocity (no change)
        return {skill: 0.0 for skill in current_skill_scores.keys()}