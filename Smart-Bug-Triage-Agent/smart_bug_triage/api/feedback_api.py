"""FastAPI endpoints for feedback collection system."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Query, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from ..database.connection import get_db_session
from ..models.database import AssignmentFeedback, Assignment, Developer, Bug
from ..models.common import AssignmentFeedback as FeedbackModel


logger = logging.getLogger(__name__)


# Pydantic models for API requests/responses
class FeedbackRequest(BaseModel):
    """Request model for submitting feedback."""
    assignment_id: str = Field(..., description="ID of the assignment being rated")
    rating: int = Field(..., ge=1, le=5, description="Rating from 1-5")
    comments: Optional[str] = Field(None, max_length=1000, description="Optional feedback comments")
    resolution_time: Optional[int] = Field(None, ge=0, description="Resolution time in minutes")
    was_appropriate: bool = Field(..., description="Whether the assignment was appropriate")

    @validator('comments')
    def validate_comments(cls, v):
        if v is not None and len(v.strip()) == 0:
            return None
        return v


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""
    id: str
    assignment_id: str
    developer_id: str
    rating: int
    comments: Optional[str]
    resolution_time: Optional[int]
    was_appropriate: bool
    feedback_timestamp: datetime
    
    class Config:
        from_attributes = True


class FeedbackSummary(BaseModel):
    """Summary statistics for feedback."""
    total_feedback_count: int
    average_rating: float
    appropriate_assignment_rate: float
    average_resolution_time: Optional[float]
    rating_distribution: Dict[int, int]


class DeveloperFeedbackStats(BaseModel):
    """Feedback statistics for a specific developer."""
    developer_id: str
    developer_name: str
    total_assignments: int
    feedback_count: int
    average_rating: Optional[float]
    appropriate_rate: Optional[float]
    average_resolution_time: Optional[float]
    recent_feedback_trend: List[Dict[str, Any]]


class FeedbackAnalytics(BaseModel):
    """Comprehensive feedback analytics."""
    overall_summary: FeedbackSummary
    developer_stats: List[DeveloperFeedbackStats]
    category_performance: Dict[str, Dict[str, Any]]
    time_series_data: List[Dict[str, Any]]


class FeedbackAPI:
    """FastAPI application for feedback collection."""
    
    def __init__(self):
        self.app = FastAPI(
            title="Smart Bug Triage Feedback API",
            description="API for collecting and analyzing assignment feedback",
            version="1.0.0"
        )
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up API routes."""
        
        @self.app.post("/feedback", response_model=FeedbackResponse)
        async def submit_feedback(
            feedback_request: FeedbackRequest,
            db: Session = Depends(get_db_session)
        ):
            """Submit feedback for an assignment."""
            return self._submit_feedback(db, feedback_request)
        
        @self.app.get("/feedback/{feedback_id}", response_model=FeedbackResponse)
        async def get_feedback(
            feedback_id: str = Path(..., description="Feedback ID"),
            db: Session = Depends(get_db_session)
        ):
            """Get specific feedback by ID."""
            return self._get_feedback(db, feedback_id)
        
        @self.app.get("/feedback", response_model=List[FeedbackResponse])
        async def list_feedback(
            developer_id: Optional[str] = Query(None, description="Filter by developer ID"),
            assignment_id: Optional[str] = Query(None, description="Filter by assignment ID"),
            rating_min: Optional[int] = Query(None, ge=1, le=5, description="Minimum rating filter"),
            rating_max: Optional[int] = Query(None, ge=1, le=5, description="Maximum rating filter"),
            days_back: Optional[int] = Query(30, ge=1, le=365, description="Days to look back"),
            limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
            offset: int = Query(0, ge=0, description="Offset for pagination"),
            db: Session = Depends(get_db_session)
        ):
            """List feedback with optional filters."""
            return self._list_feedback(
                db, developer_id, assignment_id, rating_min, rating_max, 
                days_back, limit, offset
            )
        
        @self.app.get("/feedback/analytics", response_model=FeedbackAnalytics)
        async def get_feedback_analytics(
            days_back: int = Query(30, ge=1, le=365, description="Days to analyze"),
            db: Session = Depends(get_db_session)
        ):
            """Get comprehensive feedback analytics."""
            return self._get_feedback_analytics(db, days_back)
        
        @self.app.get("/feedback/summary", response_model=FeedbackSummary)
        async def get_feedback_summary(
            days_back: int = Query(30, ge=1, le=365, description="Days to analyze"),
            db: Session = Depends(get_db_session)
        ):
            """Get feedback summary statistics."""
            return self._get_feedback_summary(db, days_back)
        
        @self.app.get("/developers/{developer_id}/feedback", response_model=DeveloperFeedbackStats)
        async def get_developer_feedback_stats(
            developer_id: str = Path(..., description="Developer ID"),
            days_back: int = Query(30, ge=1, le=365, description="Days to analyze"),
            db: Session = Depends(get_db_session)
        ):
            """Get feedback statistics for a specific developer."""
            return self._get_developer_feedback_stats(db, developer_id, days_back)
        
        @self.app.delete("/feedback/{feedback_id}")
        async def delete_feedback(
            feedback_id: str = Path(..., description="Feedback ID"),
            db: Session = Depends(get_db_session)
        ):
            """Delete feedback (admin only)."""
            return self._delete_feedback(db, feedback_id)
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.utcnow()}
    
    def _submit_feedback(self, db: Session, feedback_request: FeedbackRequest) -> FeedbackResponse:
        """Submit new feedback for an assignment."""
        try:
            # Verify assignment exists
            assignment = db.query(Assignment).filter(
                Assignment.id == feedback_request.assignment_id
            ).first()
            
            if not assignment:
                raise HTTPException(
                    status_code=404,
                    detail=f"Assignment {feedback_request.assignment_id} not found"
                )
            
            # Check if feedback already exists for this assignment
            existing_feedback = db.query(AssignmentFeedback).filter(
                AssignmentFeedback.assignment_id == feedback_request.assignment_id
            ).first()
            
            if existing_feedback:
                raise HTTPException(
                    status_code=409,
                    detail=f"Feedback already exists for assignment {feedback_request.assignment_id}"
                )
            
            # Create new feedback record
            feedback = AssignmentFeedback(
                id=str(uuid4()),
                assignment_id=feedback_request.assignment_id,
                developer_id=assignment.developer_id,
                rating=feedback_request.rating,
                comments=feedback_request.comments,
                resolution_time=feedback_request.resolution_time,
                was_appropriate=feedback_request.was_appropriate,
                feedback_timestamp=datetime.utcnow()
            )
            
            db.add(feedback)
            db.commit()
            db.refresh(feedback)
            
            logger.info(f"Feedback submitted for assignment {feedback_request.assignment_id}")
            
            return FeedbackResponse.from_orm(feedback)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting feedback: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")
    
    def _get_feedback(self, db: Session, feedback_id: str) -> FeedbackResponse:
        """Get specific feedback by ID."""
        feedback = db.query(AssignmentFeedback).filter(
            AssignmentFeedback.id == feedback_id
        ).first()
        
        if not feedback:
            raise HTTPException(
                status_code=404,
                detail=f"Feedback {feedback_id} not found"
            )
        
        return FeedbackResponse.from_orm(feedback)
    
    def _list_feedback(
        self,
        db: Session,
        developer_id: Optional[str],
        assignment_id: Optional[str],
        rating_min: Optional[int],
        rating_max: Optional[int],
        days_back: int,
        limit: int,
        offset: int
    ) -> List[FeedbackResponse]:
        """List feedback with filters."""
        query = db.query(AssignmentFeedback)
        
        # Apply filters
        if developer_id:
            query = query.filter(AssignmentFeedback.developer_id == developer_id)
        
        if assignment_id:
            query = query.filter(AssignmentFeedback.assignment_id == assignment_id)
        
        if rating_min is not None:
            query = query.filter(AssignmentFeedback.rating >= rating_min)
        
        if rating_max is not None:
            query = query.filter(AssignmentFeedback.rating <= rating_max)
        
        # Time filter
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        query = query.filter(AssignmentFeedback.feedback_timestamp >= cutoff_date)
        
        # Order and paginate
        query = query.order_by(desc(AssignmentFeedback.feedback_timestamp))
        query = query.offset(offset).limit(limit)
        
        feedback_list = query.all()
        return [FeedbackResponse.from_orm(f) for f in feedback_list]
    
    def _get_feedback_summary(self, db: Session, days_back: int) -> FeedbackSummary:
        """Get feedback summary statistics."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Basic statistics
        feedback_query = db.query(AssignmentFeedback).filter(
            AssignmentFeedback.feedback_timestamp >= cutoff_date
        )
        
        total_count = feedback_query.count()
        
        if total_count == 0:
            return FeedbackSummary(
                total_feedback_count=0,
                average_rating=0.0,
                appropriate_assignment_rate=0.0,
                average_resolution_time=None,
                rating_distribution={}
            )
        
        # Calculate averages
        avg_rating = db.query(func.avg(AssignmentFeedback.rating)).filter(
            AssignmentFeedback.feedback_timestamp >= cutoff_date
        ).scalar() or 0.0
        
        appropriate_count = feedback_query.filter(
            AssignmentFeedback.was_appropriate == True
        ).count()
        appropriate_rate = appropriate_count / total_count if total_count > 0 else 0.0
        
        # Average resolution time (only for feedback with resolution time)
        avg_resolution = db.query(func.avg(AssignmentFeedback.resolution_time)).filter(
            and_(
                AssignmentFeedback.feedback_timestamp >= cutoff_date,
                AssignmentFeedback.resolution_time.isnot(None)
            )
        ).scalar()
        
        # Rating distribution
        rating_dist = {}
        for rating in range(1, 6):
            count = feedback_query.filter(AssignmentFeedback.rating == rating).count()
            rating_dist[rating] = count
        
        return FeedbackSummary(
            total_feedback_count=total_count,
            average_rating=round(avg_rating, 2),
            appropriate_assignment_rate=round(appropriate_rate, 2),
            average_resolution_time=round(avg_resolution, 2) if avg_resolution else None,
            rating_distribution=rating_dist
        )
    
    def _get_developer_feedback_stats(
        self, 
        db: Session, 
        developer_id: str, 
        days_back: int
    ) -> DeveloperFeedbackStats:
        """Get feedback statistics for a specific developer."""
        # Verify developer exists
        developer = db.query(Developer).filter(Developer.id == developer_id).first()
        if not developer:
            raise HTTPException(
                status_code=404,
                detail=f"Developer {developer_id} not found"
            )
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Total assignments in period
        total_assignments = db.query(Assignment).filter(
            and_(
                Assignment.developer_id == developer_id,
                Assignment.assigned_at >= cutoff_date
            )
        ).count()
        
        # Feedback statistics
        feedback_query = db.query(AssignmentFeedback).filter(
            and_(
                AssignmentFeedback.developer_id == developer_id,
                AssignmentFeedback.feedback_timestamp >= cutoff_date
            )
        )
        
        feedback_count = feedback_query.count()
        
        avg_rating = None
        appropriate_rate = None
        avg_resolution = None
        
        if feedback_count > 0:
            avg_rating = db.query(func.avg(AssignmentFeedback.rating)).filter(
                and_(
                    AssignmentFeedback.developer_id == developer_id,
                    AssignmentFeedback.feedback_timestamp >= cutoff_date
                )
            ).scalar()
            
            appropriate_count = feedback_query.filter(
                AssignmentFeedback.was_appropriate == True
            ).count()
            appropriate_rate = appropriate_count / feedback_count
            
            avg_resolution = db.query(func.avg(AssignmentFeedback.resolution_time)).filter(
                and_(
                    AssignmentFeedback.developer_id == developer_id,
                    AssignmentFeedback.feedback_timestamp >= cutoff_date,
                    AssignmentFeedback.resolution_time.isnot(None)
                )
            ).scalar()
        
        # Recent feedback trend (last 7 days)
        recent_feedback = []
        for i in range(7):
            day_start = datetime.utcnow() - timedelta(days=i+1)
            day_end = datetime.utcnow() - timedelta(days=i)
            
            day_feedback = db.query(AssignmentFeedback).filter(
                and_(
                    AssignmentFeedback.developer_id == developer_id,
                    AssignmentFeedback.feedback_timestamp >= day_start,
                    AssignmentFeedback.feedback_timestamp < day_end
                )
            ).all()
            
            if day_feedback:
                day_avg_rating = sum(f.rating for f in day_feedback) / len(day_feedback)
                day_appropriate_rate = sum(1 for f in day_feedback if f.was_appropriate) / len(day_feedback)
            else:
                day_avg_rating = None
                day_appropriate_rate = None
            
            recent_feedback.append({
                "date": day_start.date().isoformat(),
                "feedback_count": len(day_feedback),
                "average_rating": round(day_avg_rating, 2) if day_avg_rating else None,
                "appropriate_rate": round(day_appropriate_rate, 2) if day_appropriate_rate else None
            })
        
        return DeveloperFeedbackStats(
            developer_id=developer_id,
            developer_name=developer.name,
            total_assignments=total_assignments,
            feedback_count=feedback_count,
            average_rating=round(avg_rating, 2) if avg_rating else None,
            appropriate_rate=round(appropriate_rate, 2) if appropriate_rate else None,
            average_resolution_time=round(avg_resolution, 2) if avg_resolution else None,
            recent_feedback_trend=recent_feedback
        )
    
    def _get_feedback_analytics(self, db: Session, days_back: int) -> FeedbackAnalytics:
        """Get comprehensive feedback analytics."""
        # Overall summary
        overall_summary = self._get_feedback_summary(db, days_back)
        
        # Developer statistics
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        developers_with_assignments = db.query(Assignment.developer_id).filter(
            Assignment.assigned_at >= cutoff_date
        ).distinct().all()
        
        developer_stats = []
        for (dev_id,) in developers_with_assignments:
            try:
                stats = self._get_developer_feedback_stats(db, dev_id, days_back)
                developer_stats.append(stats)
            except HTTPException:
                continue  # Skip if developer not found
        
        # Category performance
        category_performance = self._get_category_performance(db, days_back)
        
        # Time series data (daily aggregates)
        time_series_data = self._get_time_series_data(db, days_back)
        
        return FeedbackAnalytics(
            overall_summary=overall_summary,
            developer_stats=developer_stats,
            category_performance=category_performance,
            time_series_data=time_series_data
        )
    
    def _get_category_performance(self, db: Session, days_back: int) -> Dict[str, Dict[str, Any]]:
        """Get performance statistics by bug category."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Join feedback with assignments and bugs to get categories
        results = db.query(
            Bug.category,
            func.count(AssignmentFeedback.id).label('feedback_count'),
            func.avg(AssignmentFeedback.rating).label('avg_rating'),
            func.avg(AssignmentFeedback.resolution_time).label('avg_resolution'),
            func.sum(func.cast(AssignmentFeedback.was_appropriate, db.bind.dialect.name == 'postgresql' and 'integer' or 'signed')).label('appropriate_count')
        ).join(
            Assignment, AssignmentFeedback.assignment_id == Assignment.id
        ).join(
            Bug, Assignment.bug_id == Bug.id
        ).filter(
            AssignmentFeedback.feedback_timestamp >= cutoff_date
        ).group_by(Bug.category).all()
        
        category_performance = {}
        for result in results:
            if result.category:
                appropriate_rate = (result.appropriate_count / result.feedback_count) if result.feedback_count > 0 else 0
                category_performance[result.category.value] = {
                    'feedback_count': result.feedback_count,
                    'average_rating': round(result.avg_rating, 2) if result.avg_rating else 0,
                    'average_resolution_time': round(result.avg_resolution, 2) if result.avg_resolution else None,
                    'appropriate_assignment_rate': round(appropriate_rate, 2)
                }
        
        return category_performance
    
    def _get_time_series_data(self, db: Session, days_back: int) -> List[Dict[str, Any]]:
        """Get daily time series data for feedback trends."""
        time_series = []
        
        for i in range(days_back):
            day_start = datetime.utcnow() - timedelta(days=i+1)
            day_end = datetime.utcnow() - timedelta(days=i)
            
            day_feedback = db.query(AssignmentFeedback).filter(
                and_(
                    AssignmentFeedback.feedback_timestamp >= day_start,
                    AssignmentFeedback.feedback_timestamp < day_end
                )
            ).all()
            
            if day_feedback:
                avg_rating = sum(f.rating for f in day_feedback) / len(day_feedback)
                appropriate_count = sum(1 for f in day_feedback if f.was_appropriate)
                appropriate_rate = appropriate_count / len(day_feedback)
                
                resolution_times = [f.resolution_time for f in day_feedback if f.resolution_time is not None]
                avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else None
            else:
                avg_rating = None
                appropriate_rate = None
                avg_resolution = None
            
            time_series.append({
                'date': day_start.date().isoformat(),
                'feedback_count': len(day_feedback),
                'average_rating': round(avg_rating, 2) if avg_rating else None,
                'appropriate_assignment_rate': round(appropriate_rate, 2) if appropriate_rate else None,
                'average_resolution_time': round(avg_resolution, 2) if avg_resolution else None
            })
        
        return list(reversed(time_series))  # Return chronological order
    
    def _delete_feedback(self, db: Session, feedback_id: str) -> JSONResponse:
        """Delete feedback (admin function)."""
        feedback = db.query(AssignmentFeedback).filter(
            AssignmentFeedback.id == feedback_id
        ).first()
        
        if not feedback:
            raise HTTPException(
                status_code=404,
                detail=f"Feedback {feedback_id} not found"
            )
        
        db.delete(feedback)
        db.commit()
        
        logger.info(f"Feedback {feedback_id} deleted")
        return JSONResponse(
            status_code=200,
            content={"message": f"Feedback {feedback_id} deleted successfully"}
        )


def create_feedback_api() -> FastAPI:
    """Create and configure the feedback API application."""
    feedback_api = FeedbackAPI()
    return feedback_api.app