"""System metrics collection and storage."""

import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from smart_bug_triage.database.connection import get_db_session
from smart_bug_triage.models.database import SystemMetric, ProcessingMetrics
from smart_bug_triage.utils.logging import get_logger


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    metric_type: str
    tags: Dict[str, str]
    timestamp: datetime


class MetricsCollector:
    """Enhanced metrics collector with database persistence."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self._buffer: List[MetricPoint] = []
        self._buffer_size = 100
        
    def record_counter(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a counter metric (cumulative value)."""
        self._record_metric(name, value, 'counter', tags or {})
    
    def record_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a gauge metric (current value)."""
        self._record_metric(name, value, 'gauge', tags or {})
    
    def record_timer(self, name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a timer metric (duration in milliseconds)."""
        self._record_metric(name, duration_ms, 'timer', tags or {})
    
    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram metric (distribution of values)."""
        self._record_metric(name, value, 'histogram', tags or {})
    
    def _record_metric(self, name: str, value: float, metric_type: str, tags: Dict[str, str]) -> None:
        """Internal method to record a metric."""
        metric_point = MetricPoint(
            name=name,
            value=value,
            metric_type=metric_type,
            tags=tags,
            timestamp=datetime.now()
        )
        
        self._buffer.append(metric_point)
        
        # Flush buffer if it's full
        if len(self._buffer) >= self._buffer_size:
            self.flush_metrics()
    
    def flush_metrics(self) -> None:
        """Flush buffered metrics to database."""
        if not self._buffer:
            return
            
        try:
            with get_db_session() as session:
                metrics_to_insert = []
                for metric_point in self._buffer:
                    db_metric = SystemMetric(
                        metric_name=metric_point.name,
                        metric_value=metric_point.value,
                        metric_type=metric_point.metric_type,
                        tags=metric_point.tags,
                        timestamp=metric_point.timestamp
                    )
                    metrics_to_insert.append(db_metric)
                
                session.add_all(metrics_to_insert)
                session.commit()
                
                self.logger.debug(f"Flushed {len(self._buffer)} metrics to database")
                self._buffer.clear()
                
        except Exception as e:
            self.logger.error(f"Failed to flush metrics to database: {str(e)}")
    
    def get_metric_stats(self, metric_name: str, window_minutes: int = 60) -> Dict[str, float]:
        """Get statistics for a metric within a time window."""
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        
        try:
            with get_db_session() as session:
                query = session.query(
                    func.count(SystemMetric.metric_value).label('count'),
                    func.avg(SystemMetric.metric_value).label('avg'),
                    func.min(SystemMetric.metric_value).label('min'),
                    func.max(SystemMetric.metric_value).label('max'),
                    func.sum(SystemMetric.metric_value).label('sum')
                ).filter(
                    and_(
                        SystemMetric.metric_name == metric_name,
                        SystemMetric.timestamp >= cutoff_time
                    )
                )
                
                result = query.first()
                
                return {
                    'count': result.count or 0,
                    'avg': float(result.avg or 0),
                    'min': float(result.min or 0),
                    'max': float(result.max or 0),
                    'sum': float(result.sum or 0)
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get metric stats: {str(e)}")
            return {'count': 0, 'avg': 0, 'min': 0, 'max': 0, 'sum': 0}
    
    def get_metrics_by_type(self, metric_type: str, window_minutes: int = 60) -> List[Dict[str, Any]]:
        """Get all metrics of a specific type within a time window."""
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        
        try:
            with get_db_session() as session:
                metrics = session.query(SystemMetric).filter(
                    and_(
                        SystemMetric.metric_type == metric_type,
                        SystemMetric.timestamp >= cutoff_time
                    )
                ).order_by(SystemMetric.timestamp.desc()).all()
                
                return [
                    {
                        'name': metric.metric_name,
                        'value': metric.metric_value,
                        'tags': metric.tags,
                        'timestamp': metric.timestamp.isoformat()
                    }
                    for metric in metrics
                ]
                
        except Exception as e:
            self.logger.error(f"Failed to get metrics by type: {str(e)}")
            return []


class SystemMetricsCollector:
    """Collects system-wide performance metrics."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.logger = get_logger(__name__)
    
    def record_bug_processing_time(self, bug_id: str, process_type: str, 
                                 start_time: datetime, success: bool = True, 
                                 error_message: Optional[str] = None) -> None:
        """Record processing time for bug-related operations."""
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        # Record to metrics collector
        self.metrics.record_timer(
            f'bug_processing_time_{process_type}',
            duration_ms,
            {'success': str(success), 'bug_id': bug_id}
        )
        
        # Record to processing metrics table
        try:
            with get_db_session() as session:
                processing_metric = ProcessingMetrics(
                    process_type=process_type,
                    process_id=bug_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message
                )
                session.add(processing_metric)
                session.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to record processing metric: {str(e)}")
    
    def record_assignment_metrics(self, assignment_id: str, developer_count: int, 
                                confidence_score: float) -> None:
        """Record metrics related to bug assignments."""
        self.metrics.record_gauge('assignment_confidence', confidence_score, 
                                {'assignment_id': assignment_id})
        self.metrics.record_gauge('available_developers', developer_count)
        self.metrics.record_counter('assignments_made', 1.0, 
                                  {'assignment_id': assignment_id})
    
    def record_agent_heartbeat(self, agent_id: str, agent_type: str) -> None:
        """Record agent heartbeat for health monitoring."""
        self.metrics.record_counter('agent_heartbeat', 1.0, 
                                  {'agent_id': agent_id, 'agent_type': agent_type})
    
    def record_api_call_metrics(self, api_name: str, duration_ms: float, 
                              success: bool, status_code: Optional[int] = None) -> None:
        """Record external API call metrics."""
        tags = {
            'api': api_name,
            'success': str(success)
        }
        if status_code:
            tags['status_code'] = str(status_code)
            
        self.metrics.record_timer(f'api_call_duration_{api_name}', duration_ms, tags)
        self.metrics.record_counter(f'api_calls_{api_name}', 1.0, tags)
    
    def record_queue_metrics(self, queue_name: str, message_count: int, 
                           processing_time_ms: Optional[float] = None) -> None:
        """Record message queue metrics."""
        self.metrics.record_gauge(f'queue_depth_{queue_name}', message_count)
        
        if processing_time_ms is not None:
            self.metrics.record_timer(f'queue_processing_time_{queue_name}', 
                                    processing_time_ms)
    
    def record_accuracy_metrics(self, category_accuracy: float, 
                              assignment_accuracy: float) -> None:
        """Record system accuracy metrics."""
        self.metrics.record_gauge('category_classification_accuracy', category_accuracy)
        self.metrics.record_gauge('assignment_accuracy', assignment_accuracy)
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Get a summary of system health metrics."""
        try:
            # Get recent processing times
            processing_stats = self.metrics.get_metric_stats('bug_processing_time_triage', 15)
            assignment_stats = self.metrics.get_metric_stats('assignment_confidence', 60)
            
            # Get error rates
            with get_db_session() as session:
                recent_time = datetime.now() - timedelta(hours=1)
                
                total_processes = session.query(ProcessingMetrics).filter(
                    ProcessingMetrics.start_time >= recent_time
                ).count()
                
                failed_processes = session.query(ProcessingMetrics).filter(
                    and_(
                        ProcessingMetrics.start_time >= recent_time,
                        ProcessingMetrics.success == False
                    )
                ).count()
                
                error_rate = (failed_processes / total_processes * 100) if total_processes > 0 else 0
            
            return {
                'avg_processing_time_ms': processing_stats['avg'],
                'avg_assignment_confidence': assignment_stats['avg'],
                'error_rate_percent': error_rate,
                'total_processes_last_hour': total_processes,
                'failed_processes_last_hour': failed_processes,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get system health summary: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


# Global instance
metrics_collector = MetricsCollector()
system_metrics = SystemMetricsCollector(metrics_collector)