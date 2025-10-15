"""Performance monitoring for processing time and throughput."""

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from smart_bug_triage.database.connection import get_db_session
from smart_bug_triage.models.database import ProcessingMetrics, SystemMetric
from smart_bug_triage.utils.logging import get_logger


@dataclass
class PerformanceMetrics:
    """Performance metrics for a specific process type."""
    process_type: str
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    p95_duration_ms: float
    total_processes: int
    success_rate: float
    throughput_per_hour: float
    error_count: int
    time_period: str


@dataclass
class ThroughputMetrics:
    """Throughput metrics over time."""
    process_type: str
    hourly_throughput: List[Tuple[str, int]]  # (hour, count)
    daily_throughput: List[Tuple[str, int]]   # (date, count)
    peak_hour: str
    peak_throughput: int
    avg_throughput: float


class PerformanceMonitor:
    """Monitors system performance metrics."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def get_performance_metrics(self, process_type: Optional[str] = None, 
                              hours: int = 24) -> Dict[str, PerformanceMetrics]:
        """Get performance metrics for specified process types."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            with get_db_session() as session:
                query = session.query(ProcessingMetrics).filter(
                    ProcessingMetrics.start_time >= cutoff_time
                )
                
                if process_type:
                    query = query.filter(ProcessingMetrics.process_type == process_type)
                
                metrics_data = query.all()
                
                # Group by process type
                process_groups = {}
                for metric in metrics_data:
                    ptype = metric.process_type
                    if ptype not in process_groups:
                        process_groups[ptype] = []
                    process_groups[ptype].append(metric)
                
                # Calculate metrics for each process type
                results = {}
                for ptype, metrics_list in process_groups.items():
                    results[ptype] = self._calculate_process_metrics(metrics_list, hours)
                
                return results
                
        except Exception as e:
            self.logger.error(f"Failed to get performance metrics: {str(e)}")
            return {}
    
    def _calculate_process_metrics(self, metrics_list: List[ProcessingMetrics], 
                                 hours: int) -> PerformanceMetrics:
        """Calculate performance metrics for a list of processing records."""
        if not metrics_list:
            return PerformanceMetrics(
                process_type="unknown",
                avg_duration_ms=0.0,
                min_duration_ms=0.0,
                max_duration_ms=0.0,
                p95_duration_ms=0.0,
                total_processes=0,
                success_rate=0.0,
                throughput_per_hour=0.0,
                error_count=0,
                time_period=f"Last {hours} hours"
            )
        
        durations = [m.duration_ms for m in metrics_list]
        successful = [m for m in metrics_list if m.success]
        
        # Calculate duration statistics
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        
        # Calculate 95th percentile
        sorted_durations = sorted(durations)
        p95_index = int(0.95 * len(sorted_durations))
        p95_duration = sorted_durations[p95_index] if sorted_durations else 0
        
        # Calculate success rate
        success_rate = (len(successful) / len(metrics_list)) * 100
        
        # Calculate throughput
        throughput_per_hour = len(metrics_list) / hours
        
        # Count errors
        error_count = len([m for m in metrics_list if not m.success])
        
        return PerformanceMetrics(
            process_type=metrics_list[0].process_type,
            avg_duration_ms=avg_duration,
            min_duration_ms=min_duration,
            max_duration_ms=max_duration,
            p95_duration_ms=p95_duration,
            total_processes=len(metrics_list),
            success_rate=success_rate,
            throughput_per_hour=throughput_per_hour,
            error_count=error_count,
            time_period=f"Last {hours} hours"
        )
    
    def get_throughput_metrics(self, process_type: str, days: int = 7) -> ThroughputMetrics:
        """Get throughput metrics over time."""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            with get_db_session() as session:
                # Get hourly throughput
                hourly_data = session.query(
                    func.date_trunc('hour', ProcessingMetrics.start_time).label('hour'),
                    func.count(ProcessingMetrics.id).label('count')
                ).filter(
                    and_(
                        ProcessingMetrics.process_type == process_type,
                        ProcessingMetrics.start_time >= cutoff_time
                    )
                ).group_by(
                    func.date_trunc('hour', ProcessingMetrics.start_time)
                ).order_by('hour').all()
                
                # Get daily throughput
                daily_data = session.query(
                    func.date(ProcessingMetrics.start_time).label('date'),
                    func.count(ProcessingMetrics.id).label('count')
                ).filter(
                    and_(
                        ProcessingMetrics.process_type == process_type,
                        ProcessingMetrics.start_time >= cutoff_time
                    )
                ).group_by(
                    func.date(ProcessingMetrics.start_time)
                ).order_by('date').all()
                
                # Format results
                hourly_throughput = [(str(row.hour), row.count) for row in hourly_data]
                daily_throughput = [(str(row.date), row.count) for row in daily_data]
                
                # Find peak hour and throughput
                peak_hour = ""
                peak_throughput = 0
                if hourly_data:
                    peak_row = max(hourly_data, key=lambda x: x.count)
                    peak_hour = str(peak_row.hour)
                    peak_throughput = peak_row.count
                
                # Calculate average throughput
                total_items = sum(row.count for row in hourly_data)
                avg_throughput = total_items / len(hourly_data) if hourly_data else 0
                
                return ThroughputMetrics(
                    process_type=process_type,
                    hourly_throughput=hourly_throughput,
                    daily_throughput=daily_throughput,
                    peak_hour=peak_hour,
                    peak_throughput=peak_throughput,
                    avg_throughput=avg_throughput
                )
                
        except Exception as e:
            self.logger.error(f"Failed to get throughput metrics: {str(e)}")
            return ThroughputMetrics(
                process_type=process_type,
                hourly_throughput=[],
                daily_throughput=[],
                peak_hour="",
                peak_throughput=0,
                avg_throughput=0.0
            )
    
    def get_slow_processes(self, process_type: str, threshold_ms: int = 5000, 
                          hours: int = 24) -> List[Dict[str, Any]]:
        """Get processes that took longer than the threshold."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            with get_db_session() as session:
                slow_processes = session.query(ProcessingMetrics).filter(
                    and_(
                        ProcessingMetrics.process_type == process_type,
                        ProcessingMetrics.duration_ms > threshold_ms,
                        ProcessingMetrics.start_time >= cutoff_time
                    )
                ).order_by(desc(ProcessingMetrics.duration_ms)).limit(50).all()
                
                return [
                    {
                        'process_id': proc.process_id,
                        'duration_ms': proc.duration_ms,
                        'start_time': proc.start_time.isoformat(),
                        'success': proc.success,
                        'error_message': proc.error_message
                    }
                    for proc in slow_processes
                ]
                
        except Exception as e:
            self.logger.error(f"Failed to get slow processes: {str(e)}")
            return []
    
    def get_error_analysis(self, process_type: Optional[str] = None, 
                          hours: int = 24) -> Dict[str, Any]:
        """Analyze errors in processing."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            with get_db_session() as session:
                query = session.query(ProcessingMetrics).filter(
                    and_(
                        ProcessingMetrics.success == False,
                        ProcessingMetrics.start_time >= cutoff_time
                    )
                )
                
                if process_type:
                    query = query.filter(ProcessingMetrics.process_type == process_type)
                
                error_records = query.all()
                
                # Group errors by message
                error_groups = {}
                for record in error_records:
                    error_msg = record.error_message or "Unknown error"
                    if error_msg not in error_groups:
                        error_groups[error_msg] = []
                    error_groups[error_msg].append(record)
                
                # Sort by frequency
                error_summary = []
                for error_msg, records in error_groups.items():
                    error_summary.append({
                        'error_message': error_msg,
                        'count': len(records),
                        'process_types': list(set(r.process_type for r in records)),
                        'first_occurrence': min(r.start_time for r in records).isoformat(),
                        'last_occurrence': max(r.start_time for r in records).isoformat()
                    })
                
                error_summary.sort(key=lambda x: x['count'], reverse=True)
                
                return {
                    'total_errors': len(error_records),
                    'unique_error_types': len(error_groups),
                    'error_breakdown': error_summary[:10],  # Top 10 errors
                    'time_period': f"Last {hours} hours"
                }
                
        except Exception as e:
            self.logger.error(f"Failed to analyze errors: {str(e)}")
            return {'error': str(e)}
    
    def get_performance_trends(self, process_type: str, days: int = 30) -> Dict[str, List[Tuple[str, float]]]:
        """Get performance trends over time."""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            with get_db_session() as session:
                # Get daily average duration
                daily_avg_duration = session.query(
                    func.date(ProcessingMetrics.start_time).label('date'),
                    func.avg(ProcessingMetrics.duration_ms).label('avg_duration')
                ).filter(
                    and_(
                        ProcessingMetrics.process_type == process_type,
                        ProcessingMetrics.start_time >= cutoff_time
                    )
                ).group_by(
                    func.date(ProcessingMetrics.start_time)
                ).order_by('date').all()
                
                # Get daily success rate
                daily_success_rate = session.query(
                    func.date(ProcessingMetrics.start_time).label('date'),
                    (func.sum(func.cast(ProcessingMetrics.success, func.Integer())) * 100.0 / 
                     func.count(ProcessingMetrics.id)).label('success_rate')
                ).filter(
                    and_(
                        ProcessingMetrics.process_type == process_type,
                        ProcessingMetrics.start_time >= cutoff_time
                    )
                ).group_by(
                    func.date(ProcessingMetrics.start_time)
                ).order_by('date').all()
                
                # Get daily throughput
                daily_throughput = session.query(
                    func.date(ProcessingMetrics.start_time).label('date'),
                    func.count(ProcessingMetrics.id).label('throughput')
                ).filter(
                    and_(
                        ProcessingMetrics.process_type == process_type,
                        ProcessingMetrics.start_time >= cutoff_time
                    )
                ).group_by(
                    func.date(ProcessingMetrics.start_time)
                ).order_by('date').all()
                
                return {
                    'avg_duration': [(str(row.date), float(row.avg_duration)) for row in daily_avg_duration],
                    'success_rate': [(str(row.date), float(row.success_rate)) for row in daily_success_rate],
                    'throughput': [(str(row.date), row.throughput) for row in daily_throughput]
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get performance trends: {str(e)}")
            return {'avg_duration': [], 'success_rate': [], 'throughput': []}
    
    def get_system_performance_summary(self) -> Dict[str, Any]:
        """Get overall system performance summary."""
        try:
            # Get metrics for all process types in the last 24 hours
            all_metrics = self.get_performance_metrics(hours=24)
            
            # Calculate system-wide statistics
            total_processes = sum(m.total_processes for m in all_metrics.values())
            total_errors = sum(m.error_count for m in all_metrics.values())
            
            avg_success_rate = (
                sum(m.success_rate * m.total_processes for m in all_metrics.values()) / 
                total_processes if total_processes > 0 else 0
            )
            
            avg_throughput = sum(m.throughput_per_hour for m in all_metrics.values())
            
            # Find slowest process type
            slowest_process = ""
            slowest_duration = 0
            for ptype, metrics in all_metrics.items():
                if metrics.avg_duration_ms > slowest_duration:
                    slowest_duration = metrics.avg_duration_ms
                    slowest_process = ptype
            
            return {
                'total_processes_24h': total_processes,
                'total_errors_24h': total_errors,
                'system_success_rate': avg_success_rate,
                'system_throughput_per_hour': avg_throughput,
                'slowest_process_type': slowest_process,
                'slowest_avg_duration_ms': slowest_duration,
                'process_type_breakdown': {
                    ptype: {
                        'avg_duration_ms': m.avg_duration_ms,
                        'success_rate': m.success_rate,
                        'throughput_per_hour': m.throughput_per_hour
                    }
                    for ptype, m in all_metrics.items()
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get system performance summary: {str(e)}")
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}