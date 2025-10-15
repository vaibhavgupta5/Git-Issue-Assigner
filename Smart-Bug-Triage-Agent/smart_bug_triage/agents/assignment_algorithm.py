"""Assignment algorithm for matching bugs to developers."""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import math

from ..models.common import (
    CategorizedBug, DeveloperProfile, DeveloperStatus, 
    BugCategory, Priority, AvailabilityStatus
)
from ..models.database import AssignmentFeedback


@dataclass
class DeveloperScore:
    """Score breakdown for a developer candidate."""
    developer_id: str
    total_score: float
    skill_score: float
    workload_score: float
    performance_score: float
    availability_score: float
    confidence: float
    reasoning: str


@dataclass
class AssignmentResult:
    """Result of assignment algorithm."""
    developer_id: str
    confidence_score: float
    reasoning: str
    all_scores: List[DeveloperScore]


class AssignmentAlgorithm:
    """Core assignment algorithm for matching bugs to developers."""
    
    def __init__(self):
        # Scoring weights (must sum to 1.0)
        self.weights = {
            'skill_match': 0.35,
            'workload_balance': 0.25,
            'performance_history': 0.25,
            'availability': 0.15
        }
        
        # Performance decay factor (how much to weight recent vs old feedback)
        self.performance_decay_days = 30
        
        # Minimum confidence threshold for assignments
        self.min_confidence_threshold = 0.5
    
    def find_best_developer(
        self,
        bug: CategorizedBug,
        developers: List[DeveloperProfile],
        developer_statuses: List[DeveloperStatus],
        feedback_history: Dict[str, List[AssignmentFeedback]]
    ) -> Optional[AssignmentResult]:
        """
        Find the best developer for a given bug.
        
        Args:
            bug: The categorized bug to assign
            developers: List of all developer profiles
            developer_statuses: Current status of all developers
            feedback_history: Historical feedback for each developer
            
        Returns:
            AssignmentResult with best match or None if no suitable developer
        """
        if not developers:
            return None
        
        # Create status lookup for quick access
        status_lookup = {status.developer_id: status for status in developer_statuses}
        
        # Score all developers
        scores = []
        for developer in developers:
            status = status_lookup.get(developer.id)
            if not status:
                continue  # Skip developers without status
                
            score = self._score_developer(
                developer, status, bug, feedback_history.get(developer.id, [])
            )
            scores.append(score)
        
        if not scores:
            return None
        
        # Sort by total score (descending)
        scores.sort(key=lambda x: x.total_score, reverse=True)
        
        # Apply tie-breaking logic
        best_score = self._apply_tie_breaking(scores, bug)
        
        # Check if confidence meets threshold
        if best_score.confidence < self.min_confidence_threshold:
            return None
        
        return AssignmentResult(
            developer_id=best_score.developer_id,
            confidence_score=best_score.confidence,
            reasoning=best_score.reasoning,
            all_scores=scores
        )
    
    def _score_developer(
        self,
        developer: DeveloperProfile,
        status: DeveloperStatus,
        bug: CategorizedBug,
        feedback_history: List[AssignmentFeedback]
    ) -> DeveloperScore:
        """Score a single developer for the given bug."""
        
        # Calculate individual scores
        skill_score = self._calculate_skill_score(developer, bug)
        workload_score = self._calculate_workload_score(developer, status)
        performance_score = self._calculate_performance_score(feedback_history, bug.category)
        availability_score = self._calculate_availability_score(status)
        
        # Calculate weighted total score
        total_score = (
            skill_score * self.weights['skill_match'] +
            workload_score * self.weights['workload_balance'] +
            performance_score * self.weights['performance_history'] +
            availability_score * self.weights['availability']
        )
        
        # Calculate confidence based on data quality and score distribution
        confidence = self._calculate_confidence(
            skill_score, workload_score, performance_score, availability_score,
            len(feedback_history)
        )
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            developer, skill_score, workload_score, performance_score, 
            availability_score, total_score
        )
        
        return DeveloperScore(
            developer_id=developer.id,
            total_score=total_score,
            skill_score=skill_score,
            workload_score=workload_score,
            performance_score=performance_score,
            availability_score=availability_score,
            confidence=confidence,
            reasoning=reasoning
        )
    
    def _calculate_skill_score(self, developer: DeveloperProfile, bug: CategorizedBug) -> float:
        """Calculate skill match score (0.0 to 1.0)."""
        
        # Category preference bonus
        category_bonus = 0.0
        if bug.category in developer.preferred_categories:
            category_bonus = 0.3
        
        # Skill matching based on keywords and category
        skill_match = 0.0
        relevant_skills = self._get_relevant_skills_for_category(bug.category)
        
        if relevant_skills:
            matched_skills = set(skill.lower() for skill in developer.skills) & set(skill.lower() for skill in relevant_skills)
            skill_match = len(matched_skills) / len(relevant_skills)
        
        # Keyword matching
        keyword_match = 0.0
        if bug.keywords:
            developer_skills_lower = [skill.lower() for skill in developer.skills]
            matched_keywords = sum(
                1 for keyword in bug.keywords 
                if any(keyword.lower() in skill for skill in developer_skills_lower)
            )
            keyword_match = matched_keywords / len(bug.keywords)
        
        # Experience level bonus
        experience_bonus = self._get_experience_bonus(developer.experience_level, bug.severity)
        
        # Combine scores with better weighting
        base_score = (skill_match * 0.4 + keyword_match * 0.4 + category_bonus * 0.2)
        return min(1.0, base_score + experience_bonus)
    
    def _calculate_workload_score(self, developer: DeveloperProfile, status: DeveloperStatus) -> float:
        """Calculate workload balance score (0.0 to 1.0)."""
        
        if developer.max_capacity <= 0:
            return 0.0
        
        # Calculate capacity utilization
        utilization = status.current_workload / developer.max_capacity
        
        # Optimal utilization is around 70-80%
        if utilization <= 0.7:
            # Underutilized - score increases as we approach 70%
            return 0.5 + (utilization / 0.7) * 0.5
        elif utilization <= 0.8:
            # Optimal range - highest scores
            return 1.0
        elif utilization <= 1.0:
            # Getting overloaded - score decreases
            return 1.0 - ((utilization - 0.8) / 0.2) * 0.7
        else:
            # Overloaded - very low score
            return 0.1
    
    def _calculate_performance_score(
        self, 
        feedback_history: List[AssignmentFeedback], 
        bug_category: BugCategory
    ) -> float:
        """Calculate performance score based on historical feedback (0.0 to 1.0)."""
        
        if not feedback_history:
            return 0.5  # Neutral score for new developers
        
        # Filter recent feedback (within decay period)
        cutoff_date = datetime.now() - timedelta(days=self.performance_decay_days)
        recent_feedback = [
            fb for fb in feedback_history 
            if fb.feedback_timestamp >= cutoff_date
        ]
        
        if not recent_feedback:
            return 0.5
        
        # Calculate weighted average rating
        total_weight = 0.0
        weighted_sum = 0.0
        
        for feedback in recent_feedback:
            # Time-based weight (more recent = higher weight)
            days_ago = (datetime.now() - feedback.feedback_timestamp).days
            time_weight = math.exp(-days_ago / self.performance_decay_days)
            
            # Category relevance weight
            category_weight = 1.0  # Default weight
            # Could add category-specific weighting here if needed
            
            weight = time_weight * category_weight
            weighted_sum += feedback.rating * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.5
        
        # Convert 1-5 rating to 0-1 score
        avg_rating = weighted_sum / total_weight
        return (avg_rating - 1) / 4  # Maps 1-5 to 0-1
    
    def _calculate_availability_score(self, status: DeveloperStatus) -> float:
        """Calculate availability score (0.0 to 1.0)."""
        
        if status.availability == AvailabilityStatus.UNAVAILABLE:
            return 0.0
        elif status.availability == AvailabilityStatus.FOCUS_TIME:
            return 0.2
        elif status.availability == AvailabilityStatus.BUSY:
            return 0.6
        elif status.availability == AvailabilityStatus.AVAILABLE:
            base_score = 1.0
            
            # Reduce score if calendar is not free
            if not status.calendar_free:
                base_score *= 0.7
            
            # Reduce score if in focus time
            if status.focus_time_active:
                base_score *= 0.5
            
            return base_score
        
        return 0.5  # Default for unknown status
    
    def _calculate_confidence(
        self, 
        skill_score: float, 
        workload_score: float, 
        performance_score: float, 
        availability_score: float,
        feedback_count: int
    ) -> float:
        """Calculate confidence in the assignment decision."""
        
        # Base confidence from score consistency
        scores = [skill_score, workload_score, performance_score, availability_score]
        score_variance = sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)
        consistency_factor = max(0.0, 1.0 - score_variance * 2)
        
        # Data quality factor based on feedback history
        data_quality_factor = min(1.0, feedback_count / 10)  # Full confidence at 10+ feedback items
        
        # Minimum score threshold factor
        min_score = min(scores)
        threshold_factor = max(0.0, min_score)
        
        # Combine factors
        confidence = (consistency_factor * 0.4 + data_quality_factor * 0.3 + threshold_factor * 0.3)
        
        return min(1.0, max(0.0, confidence))
    
    def _apply_tie_breaking(self, scores: List[DeveloperScore], bug: CategorizedBug) -> DeveloperScore:
        """Apply tie-breaking logic for equally suitable developers."""
        
        if not scores:
            raise ValueError("No scores provided for tie-breaking")
        
        if len(scores) == 1:
            return scores[0]
        
        # Check if top scores are very close (within 5%)
        top_score = scores[0].total_score
        tied_scores = [s for s in scores if abs(s.total_score - top_score) <= 0.05]
        
        if len(tied_scores) == 1:
            return tied_scores[0]
        
        # Tie-breaking criteria in order of priority:
        
        # 1. Highest availability score
        tied_scores.sort(key=lambda x: x.availability_score, reverse=True)
        if tied_scores[0].availability_score > tied_scores[1].availability_score:
            return tied_scores[0]
        
        # 2. Highest skill score for critical/high priority bugs
        if bug.severity in [Priority.CRITICAL, Priority.HIGH]:
            tied_scores.sort(key=lambda x: x.skill_score, reverse=True)
            if tied_scores[0].skill_score > tied_scores[1].skill_score:
                return tied_scores[0]
        
        # 3. Best workload balance (closest to optimal)
        tied_scores.sort(key=lambda x: x.workload_score, reverse=True)
        if tied_scores[0].workload_score > tied_scores[1].workload_score:
            return tied_scores[0]
        
        # 4. Highest performance score
        tied_scores.sort(key=lambda x: x.performance_score, reverse=True)
        if tied_scores[0].performance_score > tied_scores[1].performance_score:
            return tied_scores[0]
        
        # 5. Highest confidence
        tied_scores.sort(key=lambda x: x.confidence, reverse=True)
        
        return tied_scores[0]
    
    def _get_relevant_skills_for_category(self, category: BugCategory) -> List[str]:
        """Get relevant skills for a bug category."""
        
        skill_mapping = {
            BugCategory.FRONTEND: ['javascript', 'react', 'vue', 'angular', 'html', 'css', 'typescript', 'ui/ux'],
            BugCategory.BACKEND: ['python', 'java', 'node.js', 'go', 'rust', 'c#', 'ruby', 'php'],
            BugCategory.DATABASE: ['sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch'],
            BugCategory.API: ['rest', 'graphql', 'api design', 'swagger', 'postman', 'microservices'],
            BugCategory.MOBILE: ['ios', 'android', 'react native', 'flutter', 'swift', 'kotlin'],
            BugCategory.SECURITY: ['security', 'authentication', 'authorization', 'encryption', 'owasp'],
            BugCategory.PERFORMANCE: ['optimization', 'profiling', 'caching', 'load testing', 'monitoring']
        }
        
        return skill_mapping.get(category, [])
    
    def _get_experience_bonus(self, experience_level: str, severity: Priority) -> float:
        """Get experience bonus based on bug severity."""
        
        experience_weights = {
            'junior': 0.0,
            'mid': 0.05,
            'senior': 0.1,
            'lead': 0.15,
            'principal': 0.2
        }
        
        base_bonus = experience_weights.get(experience_level, 0.0)
        
        # Higher bonus for critical/high severity bugs
        if severity == Priority.CRITICAL:
            return base_bonus * 2.0
        elif severity == Priority.HIGH:
            return base_bonus * 1.5
        else:
            return base_bonus
    
    def _generate_reasoning(
        self,
        developer: DeveloperProfile,
        skill_score: float,
        workload_score: float,
        performance_score: float,
        availability_score: float,
        total_score: float
    ) -> str:
        """Generate human-readable reasoning for the assignment."""
        
        reasons = []
        
        # Skill match reasoning
        if skill_score >= 0.8:
            reasons.append("excellent skill match")
        elif skill_score >= 0.6:
            reasons.append("good skill match")
        elif skill_score >= 0.4:
            reasons.append("moderate skill match")
        else:
            reasons.append("limited skill match")
        
        # Workload reasoning
        if workload_score >= 0.8:
            reasons.append("optimal workload")
        elif workload_score >= 0.6:
            reasons.append("manageable workload")
        else:
            reasons.append("high workload")
        
        # Performance reasoning
        if performance_score >= 0.8:
            reasons.append("strong performance history")
        elif performance_score >= 0.6:
            reasons.append("good performance history")
        elif performance_score >= 0.4:
            reasons.append("average performance history")
        else:
            reasons.append("limited performance data")
        
        # Availability reasoning
        if availability_score >= 0.8:
            reasons.append("immediately available")
        elif availability_score >= 0.6:
            reasons.append("mostly available")
        else:
            reasons.append("limited availability")
        
        reasoning = f"Selected {developer.name} ({developer.experience_level}) due to: {', '.join(reasons)}. "
        reasoning += f"Overall score: {total_score:.2f}"
        
        return reasoning