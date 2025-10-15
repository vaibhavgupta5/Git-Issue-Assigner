"""Advanced feedback analytics and reporting system."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import statistics

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc, case

from ..database.connection import get_db_session
from ..models.database import (
    AssignmentFeedback, Assignment, Developer, Bug, DeveloperStatus
)
from ..models.common import BugCategory, Priority


logger = logging.getLogger(__name__)


@dataclass
class TrendData:
    """Time series trend data."""
    dates: List[str]
    values: List[float]
    trend_direction: str  # 'up', 'down', 'stable'
    trend_strength: float  # 0.0 to 1.0


@dataclass
class PerformanceInsight:
    """Performance insight with actionable recommendations."""
    category: str
    insight_type: str  # 'improvement', 'concern', 'achievement'
    description: str
    impact_level: str  # 'high', 'medium', 'low'
    recommendation: str
    metrics: Dict[str, Any]


@dataclass
class FeedbackReport:
    """Comprehensive feedback analytics report."""
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    summary_metrics: Dict[str, Any]
    developer_insights: List[Dict[str, Any]]
    category_performance: Dict[str, Any]
    trends: Dict[str, TrendData]
    insights: List[PerformanceInsight]
    recommendations: List[str]


class FeedbackAnalytics:
    """Advanced analytics engine for feedback data."""
    
    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory or get_db_session
        logger.info("FeedbackAnalytics initialized")
    
    def generate_comprehensive_report(
        self, 
        days_back: int = 30,
        include_trends: bool = True,
        include_insights: bool = True
    ) -> FeedbackReport:
        """Generate a comprehensive feedback analytics report."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        with self.db_session_factory() as db:
            # Generate report components
            summary_metrics = self._calculate_summary_metrics(db, start_date, end_date)
            developer_insights = self._analyze_developer_performance(db, start_date, end_date)
            category_performance = self._analyze_category_performance(db, start_date, end_date)
            
            trends = {}
            insights = []
            recommendations = []
            
            if include_trends:
                trends = self._calculate_trends(db, start_date, end_date)
            
            if include_insights:
                insights = self._generate_insights(
                    summary_metrics, developer_insights, category_performance, trends
                )
                recommendations = self._generate_recommendations(insights)
            
            return FeedbackReport(
                report_id=f"feedback_report_{int(end_date.timestamp())}",
                generated_at=end_date,
                period_start=start_date,
                period_end=end_date,
                summary_metrics=summary_metrics,
                developer_insights=developer_insights,
                category_performance=category_performance,
                trends=trends,
                insights=insights,
                recommendations=recommendations
            )
    
    def _calculate_summary_metrics(
        self, 
        db: Session, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[str, Any]:
        """Calculate high-level summary metrics."""
        feedback_query = db.query(AssignmentFeedback).filter(
            and_(
                AssignmentFeedback.feedback_timestamp >= start_date,
                AssignmentFeedback.feedback_timestamp <= end_date
            )
        )
        
        all_feedback = feedback_query.all()
        
        if not all_feedback:
            return {
                'total_feedback': 0,
                'response_rate': 0.0,
                'average_rating': 0.0,
                'satisfaction_rate': 0.0,
                'appropriate_assignment_rate': 0.0,
                'average_resolution_time': None,
                'feedback_velocity': 0.0
            }
        
        # Basic counts and averages
        total_feedback = len(all_feedback)
        ratings = [f.rating for f in all_feedback]
        average_rating = statistics.mean(ratings)
        
        # Satisfaction rate (rating >= 4)
        satisfied_count = sum(1 for r in ratings if r >= 4)
        satisfaction_rate = satisfied_count / total_feedback
        
        # Appropriate assignment rate
        appropriate_count = sum(1 for f in all_feedback if f.was_appropriate)
        appropriate_rate = appropriate_count / total_feedback
        
        # Resolution time statistics
        resolution_times = [f.resolution_time for f in all_feedback if f.resolution_time is not None]
        avg_resolution_time = statistics.mean(resolution_times) if resolution_times else None
        
        # Response rate (feedback received vs assignments made)
        total_assignments = db.query(Assignment).filter(
            and_(
                Assignment.assigned_at >= start_date,
                Assignment.assigned_at <= end_date
            )
        ).count()
        
        response_rate = total_feedback / total_assignments if total_assignments > 0 else 0.0
        
        # Feedback velocity (feedback per day)
        period_days = (end_date - start_date).days or 1
        feedback_velocity = total_feedback / period_days
        
        return {
            'total_feedback': total_feedback,
            'total_assignments': total_assignments,
            'response_rate': round(response_rate, 3),
            'average_rating': round(average_rating, 2),
            'satisfaction_rate': round(satisfaction_rate, 3),
            'appropriate_assignment_rate': round(appropriate_rate, 3),
            'average_resolution_time': round(avg_resolution_time, 2) if avg_resolution_time else None,
            'feedback_velocity': round(feedback_velocity, 2),
            'rating_distribution': {
                str(i): sum(1 for r in ratings if r == i) for i in range(1, 6)
            }
        }
    
    def _analyze_developer_performance(
        self, 
        db: Session, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Analyze performance metrics for each developer."""
        # Get all developers with assignments in the period
        developer_assignments = db.query(
            Assignment.developer_id,
            func.count(Assignment.id).label('assignment_count')
        ).filter(
            and_(
                Assignment.assigned_at >= start_date,
                Assignment.assigned_at <= end_date
            )
        ).group_by(Assignment.developer_id).all()
        
        developer_insights = []
        
        for dev_id, assignment_count in developer_assignments:
            developer = db.query(Developer).filter(Developer.id == dev_id).first()
            if not developer:
                continue
            
            # Get feedback for this developer
            dev_feedback = db.query(AssignmentFeedback).join(
                Assignment, AssignmentFeedback.assignment_id == Assignment.id
            ).filter(
                and_(
                    Assignment.developer_id == dev_id,
                    AssignmentFeedback.feedback_timestamp >= start_date,
                    AssignmentFeedback.feedback_timestamp <= end_date
                )
            ).all()
            
            feedback_count = len(dev_feedback)
            response_rate = feedback_count / assignment_count if assignment_count > 0 else 0.0
            
            if dev_feedback:
                avg_rating = statistics.mean([f.rating for f in dev_feedback])
                appropriate_count = sum(1 for f in dev_feedback if f.was_appropriate)
                appropriate_rate = appropriate_count / feedback_count
                
                resolution_times = [f.resolution_time for f in dev_feedback if f.resolution_time is not None]
                avg_resolution_time = statistics.mean(resolution_times) if resolution_times else None
                
                # Performance trend (compare to previous period)
                prev_start = start_date - (end_date - start_date)
                prev_feedback = db.query(AssignmentFeedback).join(
                    Assignment, AssignmentFeedback.assignment_id == Assignment.id
                ).filter(
                    and_(
                        Assignment.developer_id == dev_id,
                        AssignmentFeedback.feedback_timestamp >= prev_start,
                        AssignmentFeedback.feedback_timestamp < start_date
                    )
                ).all()
                
                prev_avg_rating = statistics.mean([f.rating for f in prev_feedback]) if prev_feedback else avg_rating
                rating_trend = avg_rating - prev_avg_rating
                
                # Performance category
                if avg_rating >= 4.5 and appropriate_rate >= 0.9:
                    performance_category = "excellent"
                elif avg_rating >= 4.0 and appropriate_rate >= 0.8:
                    performance_category = "good"
                elif avg_rating >= 3.0 and appropriate_rate >= 0.7:
                    performance_category = "satisfactory"
                else:
                    performance_category = "needs_improvement"
                
            else:
                avg_rating = None
                appropriate_rate = None
                avg_resolution_time = None
                rating_trend = 0.0
                performance_category = "no_feedback"
            
            developer_insights.append({
                'developer_id': dev_id,
                'developer_name': developer.name,
                'assignment_count': assignment_count,
                'feedback_count': feedback_count,
                'response_rate': round(response_rate, 3),
                'average_rating': round(avg_rating, 2) if avg_rating else None,
                'appropriate_assignment_rate': round(appropriate_rate, 3) if appropriate_rate else None,
                'average_resolution_time': round(avg_resolution_time, 2) if avg_resolution_time else None,
                'rating_trend': round(rating_trend, 2),
                'performance_category': performance_category,
                'skills': developer.skills,
                'experience_level': developer.experience_level
            })
        
        # Sort by performance (rating, then appropriate rate)
        developer_insights.sort(
            key=lambda x: (
                x['average_rating'] or 0,
                x['appropriate_assignment_rate'] or 0
            ),
            reverse=True
        )
        
        return developer_insights
    
    def _analyze_category_performance(
        self, 
        db: Session, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[str, Any]:
        """Analyze performance by bug category."""
        category_performance = {}
        
        for category in BugCategory:
            # Get feedback for this category
            category_feedback = db.query(AssignmentFeedback).join(
                Assignment, AssignmentFeedback.assignment_id == Assignment.id
            ).join(
                Bug, Assignment.bug_id == Bug.id
            ).filter(
                and_(
                    Bug.category == category,
                    AssignmentFeedback.feedback_timestamp >= start_date,
                    AssignmentFeedback.feedback_timestamp <= end_date
                )
            ).all()
            
            if not category_feedback:
                category_performance[category.value] = {
                    'feedback_count': 0,
                    'average_rating': None,
                    'appropriate_assignment_rate': None,
                    'average_resolution_time': None,
                    'performance_trend': 'stable'
                }
                continue
            
            feedback_count = len(category_feedback)
            avg_rating = statistics.mean([f.rating for f in category_feedback])
            appropriate_count = sum(1 for f in category_feedback if f.was_appropriate)
            appropriate_rate = appropriate_count / feedback_count
            
            resolution_times = [f.resolution_time for f in category_feedback if f.resolution_time is not None]
            avg_resolution_time = statistics.mean(resolution_times) if resolution_times else None
            
            # Calculate trend compared to previous period
            prev_start = start_date - (end_date - start_date)
            prev_feedback = db.query(AssignmentFeedback).join(
                Assignment, AssignmentFeedback.assignment_id == Assignment.id
            ).join(
                Bug, Assignment.bug_id == Bug.id
            ).filter(
                and_(
                    Bug.category == category,
                    AssignmentFeedback.feedback_timestamp >= prev_start,
                    AssignmentFeedback.feedback_timestamp < start_date
                )
            ).all()
            
            if prev_feedback:
                prev_avg_rating = statistics.mean([f.rating for f in prev_feedback])
                rating_change = avg_rating - prev_avg_rating
                
                if rating_change > 0.2:
                    trend = 'improving'
                elif rating_change < -0.2:
                    trend = 'declining'
                else:
                    trend = 'stable'
            else:
                trend = 'stable'
            
            category_performance[category.value] = {
                'feedback_count': feedback_count,
                'average_rating': round(avg_rating, 2),
                'appropriate_assignment_rate': round(appropriate_rate, 3),
                'average_resolution_time': round(avg_resolution_time, 2) if avg_resolution_time else None,
                'performance_trend': trend,
                'rating_distribution': {
                    str(i): sum(1 for f in category_feedback if f.rating == i) for i in range(1, 6)
                }
            }
        
        return category_performance
    
    def _calculate_trends(
        self, 
        db: Session, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[str, TrendData]:
        """Calculate time series trends for key metrics."""
        trends = {}
        
        # Daily rating trend
        daily_ratings = self._get_daily_metric_trend(
            db, start_date, end_date, 'rating'
        )
        trends['daily_ratings'] = daily_ratings
        
        # Daily appropriate assignment rate trend
        daily_appropriate = self._get_daily_metric_trend(
            db, start_date, end_date, 'appropriate_rate'
        )
        trends['daily_appropriate_rate'] = daily_appropriate
        
        # Daily feedback volume trend
        daily_volume = self._get_daily_metric_trend(
            db, start_date, end_date, 'volume'
        )
        trends['daily_feedback_volume'] = daily_volume
        
        return trends
    
    def _get_daily_metric_trend(
        self, 
        db: Session, 
        start_date: datetime, 
        end_date: datetime, 
        metric_type: str
    ) -> TrendData:
        """Calculate daily trend for a specific metric."""
        dates = []
        values = []
        
        current_date = start_date.date()
        end_date_only = end_date.date()
        
        while current_date <= end_date_only:
            day_start = datetime.combine(current_date, datetime.min.time())
            day_end = datetime.combine(current_date, datetime.max.time())
            
            day_feedback = db.query(AssignmentFeedback).filter(
                and_(
                    AssignmentFeedback.feedback_timestamp >= day_start,
                    AssignmentFeedback.feedback_timestamp <= day_end
                )
            ).all()
            
            if metric_type == 'rating' and day_feedback:
                value = statistics.mean([f.rating for f in day_feedback])
            elif metric_type == 'appropriate_rate' and day_feedback:
                appropriate_count = sum(1 for f in day_feedback if f.was_appropriate)
                value = appropriate_count / len(day_feedback)
            elif metric_type == 'volume':
                value = len(day_feedback)
            else:
                value = 0.0
            
            dates.append(current_date.isoformat())
            values.append(value)
            
            current_date += timedelta(days=1)
        
        # Calculate trend direction and strength
        if len(values) >= 2:
            # Simple linear trend calculation
            n = len(values)
            x_values = list(range(n))
            
            # Calculate slope
            x_mean = statistics.mean(x_values)
            y_mean = statistics.mean(values)
            
            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
            denominator = sum((x - x_mean) ** 2 for x in x_values)
            
            if denominator != 0:
                slope = numerator / denominator
                
                if slope > 0.01:
                    direction = 'up'
                elif slope < -0.01:
                    direction = 'down'
                else:
                    direction = 'stable'
                
                # Trend strength based on R-squared
                y_pred = [slope * x + (y_mean - slope * x_mean) for x in x_values]
                ss_res = sum((y - y_pred) ** 2 for y, y_pred in zip(values, y_pred))
                ss_tot = sum((y - y_mean) ** 2 for y in values)
                
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
                strength = max(0.0, min(1.0, r_squared))
            else:
                direction = 'stable'
                strength = 0.0
        else:
            direction = 'stable'
            strength = 0.0
        
        return TrendData(
            dates=dates,
            values=[round(v, 3) for v in values],
            trend_direction=direction,
            trend_strength=round(strength, 3)
        )
    
    def _generate_insights(
        self,
        summary_metrics: Dict[str, Any],
        developer_insights: List[Dict[str, Any]],
        category_performance: Dict[str, Any],
        trends: Dict[str, TrendData]
    ) -> List[PerformanceInsight]:
        """Generate actionable insights from analytics data."""
        insights = []
        
        # Overall system performance insights
        if summary_metrics['satisfaction_rate'] < 0.7:
            insights.append(PerformanceInsight(
                category='system_performance',
                insight_type='concern',
                description=f"Low satisfaction rate: {summary_metrics['satisfaction_rate']:.1%}",
                impact_level='high',
                recommendation="Review assignment algorithm and developer skill matching",
                metrics={'satisfaction_rate': summary_metrics['satisfaction_rate']}
            ))
        
        if summary_metrics['response_rate'] < 0.5:
            insights.append(PerformanceInsight(
                category='feedback_collection',
                insight_type='concern',
                description=f"Low feedback response rate: {summary_metrics['response_rate']:.1%}",
                impact_level='medium',
                recommendation="Implement feedback reminders and improve feedback UX",
                metrics={'response_rate': summary_metrics['response_rate']}
            ))
        
        # Developer performance insights
        excellent_devs = [d for d in developer_insights if d['performance_category'] == 'excellent']
        needs_improvement_devs = [d for d in developer_insights if d['performance_category'] == 'needs_improvement']
        
        if excellent_devs:
            insights.append(PerformanceInsight(
                category='developer_performance',
                insight_type='achievement',
                description=f"{len(excellent_devs)} developers showing excellent performance",
                impact_level='low',
                recommendation="Consider these developers for mentoring roles or complex assignments",
                metrics={'excellent_developers': [d['developer_name'] for d in excellent_devs]}
            ))
        
        if needs_improvement_devs:
            insights.append(PerformanceInsight(
                category='developer_performance',
                insight_type='concern',
                description=f"{len(needs_improvement_devs)} developers need performance improvement",
                impact_level='medium',
                recommendation="Provide additional training or adjust assignment criteria",
                metrics={'developers_needing_improvement': [d['developer_name'] for d in needs_improvement_devs]}
            ))
        
        # Category performance insights
        poor_categories = [
            cat for cat, perf in category_performance.items()
            if perf['average_rating'] and perf['average_rating'] < 3.5
        ]
        
        if poor_categories:
            insights.append(PerformanceInsight(
                category='category_performance',
                insight_type='concern',
                description=f"Poor performance in categories: {', '.join(poor_categories)}",
                impact_level='high',
                recommendation="Review skill requirements and training for these categories",
                metrics={'poor_performing_categories': poor_categories}
            ))
        
        # Trend insights
        if 'daily_ratings' in trends:
            rating_trend = trends['daily_ratings']
            if rating_trend.trend_direction == 'down' and rating_trend.trend_strength > 0.5:
                insights.append(PerformanceInsight(
                    category='trends',
                    insight_type='concern',
                    description="Declining rating trend detected",
                    impact_level='high',
                    recommendation="Investigate recent changes in assignment algorithm or team composition",
                    metrics={'trend_strength': rating_trend.trend_strength}
                ))
            elif rating_trend.trend_direction == 'up' and rating_trend.trend_strength > 0.5:
                insights.append(PerformanceInsight(
                    category='trends',
                    insight_type='improvement',
                    description="Improving rating trend detected",
                    impact_level='low',
                    recommendation="Continue current practices and monitor for sustained improvement",
                    metrics={'trend_strength': rating_trend.trend_strength}
                ))
        
        return insights
    
    def _generate_recommendations(self, insights: List[PerformanceInsight]) -> List[str]:
        """Generate prioritized recommendations based on insights."""
        recommendations = []
        
        # Group insights by impact level
        high_impact = [i for i in insights if i.impact_level == 'high']
        medium_impact = [i for i in insights if i.impact_level == 'medium']
        
        # Add high-impact recommendations first
        for insight in high_impact:
            recommendations.append(f"HIGH PRIORITY: {insight.recommendation}")
        
        # Add medium-impact recommendations
        for insight in medium_impact:
            recommendations.append(f"MEDIUM PRIORITY: {insight.recommendation}")
        
        # Add general recommendations if no specific issues found
        if not high_impact and not medium_impact:
            recommendations.append("System performing well - continue monitoring and maintain current practices")
        
        return recommendations
    
    def export_report_to_dict(self, report: FeedbackReport) -> Dict[str, Any]:
        """Export report to dictionary format for JSON serialization."""
        return {
            'report_id': report.report_id,
            'generated_at': report.generated_at.isoformat(),
            'period_start': report.period_start.isoformat(),
            'period_end': report.period_end.isoformat(),
            'summary_metrics': report.summary_metrics,
            'developer_insights': report.developer_insights,
            'category_performance': report.category_performance,
            'trends': {k: asdict(v) for k, v in report.trends.items()},
            'insights': [asdict(insight) for insight in report.insights],
            'recommendations': report.recommendations
        }