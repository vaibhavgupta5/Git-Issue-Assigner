"""Dashboard for system status visualization."""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json

from smart_bug_triage.monitoring.metrics_collector import MetricsCollector, SystemMetricsCollector
from smart_bug_triage.monitoring.accuracy_tracker import AccuracyTracker
from smart_bug_triage.monitoring.agent_monitor import AgentHealthMonitor
from smart_bug_triage.monitoring.performance_monitor import PerformanceMonitor
from smart_bug_triage.monitoring.alert_system import AlertSystem
from smart_bug_triage.utils.logging import get_logger


@dataclass
class DashboardData:
    """Complete dashboard data structure."""
    system_health: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    accuracy_metrics: Dict[str, Any]
    agent_status: Dict[str, Any]
    active_alerts: List[Dict[str, Any]]
    recent_activity: Dict[str, Any]
    timestamp: str


class MetricsDashboard:
    """System status dashboard for monitoring and visualization."""
    
    def __init__(self, metrics_collector: MetricsCollector,
                 system_metrics: SystemMetricsCollector,
                 accuracy_tracker: AccuracyTracker,
                 agent_monitor: AgentHealthMonitor,
                 performance_monitor: PerformanceMonitor,
                 alert_system: AlertSystem):
        self.metrics_collector = metrics_collector
        self.system_metrics = system_metrics
        self.accuracy_tracker = accuracy_tracker
        self.agent_monitor = agent_monitor
        self.performance_monitor = performance_monitor
        self.alert_system = alert_system
        self.logger = get_logger(__name__)
    
    def get_dashboard_data(self) -> DashboardData:
        """Get complete dashboard data."""
        try:
            return DashboardData(
                system_health=self._get_system_health_overview(),
                performance_metrics=self._get_performance_overview(),
                accuracy_metrics=self._get_accuracy_overview(),
                agent_status=self._get_agent_status_overview(),
                active_alerts=self.alert_system.get_active_alerts(),
                recent_activity=self._get_recent_activity_overview(),
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get dashboard data: {str(e)}")
            return DashboardData(
                system_health={'error': str(e)},
                performance_metrics={'error': str(e)},
                accuracy_metrics={'error': str(e)},
                agent_status={'error': str(e)},
                active_alerts=[],
                recent_activity={'error': str(e)},
                timestamp=datetime.now().isoformat()
            )
    
    def _get_system_health_overview(self) -> Dict[str, Any]:
        """Get system health overview."""
        try:
            # Get system health summary
            health_summary = self.system_metrics.get_system_health_summary()
            
            # Get agent health summary
            agent_summary = self.agent_monitor.get_system_health_summary()
            
            # Calculate overall health score
            health_score = self._calculate_health_score(health_summary, agent_summary)
            
            return {
                'overall_health_score': health_score,
                'status': self._get_health_status(health_score),
                'avg_processing_time_ms': health_summary.get('avg_processing_time_ms', 0),
                'error_rate_percent': health_summary.get('error_rate_percent', 0),
                'total_agents': agent_summary.total_agents,
                'healthy_agents': agent_summary.healthy_agents,
                'critical_alerts': agent_summary.critical_alerts,
                'uptime_percentage': agent_summary.avg_uptime_percentage,
                'last_updated': health_summary.get('timestamp', datetime.now().isoformat())
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get system health overview: {str(e)}")
            return {'error': str(e)}
    
    def _get_performance_overview(self) -> Dict[str, Any]:
        """Get performance metrics overview."""
        try:
            # Get performance summary
            perf_summary = self.performance_monitor.get_system_performance_summary()
            
            # Get performance metrics for each process type
            process_metrics = self.performance_monitor.get_performance_metrics(hours=24)
            
            # Get throughput trends
            throughput_trends = {}
            for process_type in ['bug_detection', 'triage', 'assignment']:
                throughput_trends[process_type] = self.performance_monitor.get_throughput_metrics(
                    process_type, days=7
                )
            
            return {
                'system_summary': perf_summary,
                'process_metrics': {
                    ptype: {
                        'avg_duration_ms': metrics.avg_duration_ms,
                        'success_rate': metrics.success_rate,
                        'throughput_per_hour': metrics.throughput_per_hour,
                        'total_processes': metrics.total_processes,
                        'error_count': metrics.error_count
                    }
                    for ptype, metrics in process_metrics.items()
                },
                'throughput_trends': {
                    ptype: {
                        'daily_throughput': trends.daily_throughput[-7:],  # Last 7 days
                        'peak_throughput': trends.peak_throughput,
                        'avg_throughput': trends.avg_throughput
                    }
                    for ptype, trends in throughput_trends.items()
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get performance overview: {str(e)}")
            return {'error': str(e)}
    
    def _get_accuracy_overview(self) -> Dict[str, Any]:
        """Get accuracy metrics overview."""
        try:
            # Get accuracy report
            accuracy_report = self.accuracy_tracker.get_accuracy_report(days=30)
            
            # Get accuracy trends
            accuracy_trends = self.accuracy_tracker.get_accuracy_trends(days=30)
            
            # Get low performing areas
            low_performing = self.accuracy_tracker.get_low_performing_areas(threshold=0.7)
            
            return {
                'overall_accuracy': accuracy_report.overall_accuracy,
                'total_assignments': accuracy_report.total_assignments,
                'feedback_count': accuracy_report.feedback_count,
                'avg_resolution_time': accuracy_report.avg_resolution_time,
                'reassignment_rate': accuracy_report.reassignment_rate,
                'category_accuracy': accuracy_report.category_accuracy,
                'developer_accuracy': dict(list(accuracy_report.developer_accuracy.items())[:10]),  # Top 10
                'accuracy_trends': {
                    'overall': accuracy_trends.get('overall', [])[-30:],  # Last 30 days
                    'by_category': {
                        category: trend[-30:] for category, trend in accuracy_trends.items()
                        if category != 'overall'
                    }
                },
                'low_performing_areas': low_performing
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get accuracy overview: {str(e)}")
            return {'error': str(e)}
    
    def _get_agent_status_overview(self) -> Dict[str, Any]:
        """Get agent status overview."""
        try:
            # Get all agent health statuses
            agent_health_statuses = self.agent_monitor.get_all_agents_health()
            
            # Group by agent type
            agents_by_type = {}
            for agent in agent_health_statuses:
                agent_type = agent.agent_type
                if agent_type not in agents_by_type:
                    agents_by_type[agent_type] = []
                agents_by_type[agent_type].append({
                    'agent_id': agent.agent_id,
                    'status': agent.status,
                    'is_healthy': agent.is_healthy,
                    'last_heartbeat': agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
                    'error_count': agent.error_count,
                    'uptime_percentage': agent.uptime_percentage
                })
            
            # Calculate summary statistics
            total_agents = len(agent_health_statuses)
            healthy_agents = len([a for a in agent_health_statuses if a.is_healthy])
            
            return {
                'total_agents': total_agents,
                'healthy_agents': healthy_agents,
                'unhealthy_agents': total_agents - healthy_agents,
                'health_percentage': (healthy_agents / total_agents * 100) if total_agents > 0 else 0,
                'agents_by_type': agents_by_type,
                'agent_type_summary': {
                    agent_type: {
                        'total': len(agents),
                        'healthy': len([a for a in agents if a['is_healthy']]),
                        'avg_uptime': sum(a['uptime_percentage'] for a in agents) / len(agents) if agents else 0
                    }
                    for agent_type, agents in agents_by_type.items()
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get agent status overview: {str(e)}")
            return {'error': str(e)}
    
    def _get_recent_activity_overview(self) -> Dict[str, Any]:
        """Get recent system activity overview."""
        try:
            # Get recent metrics
            recent_counters = self.metrics_collector.get_metrics_by_type('counter', window_minutes=60)
            recent_timers = self.metrics_collector.get_metrics_by_type('timer', window_minutes=60)
            
            # Count activities by type
            activity_counts = {}
            for metric in recent_counters:
                metric_name = metric['name']
                if 'bug_processing' in metric_name or 'assignment' in metric_name:
                    activity_type = metric_name.split('_')[0]
                    activity_counts[activity_type] = activity_counts.get(activity_type, 0) + metric['value']
            
            # Get recent processing times
            processing_times = {}
            for metric in recent_timers:
                metric_name = metric['name']
                if 'processing_time' in metric_name:
                    process_type = metric_name.replace('bug_processing_time_', '')
                    if process_type not in processing_times:
                        processing_times[process_type] = []
                    processing_times[process_type].append(metric['value'])
            
            # Calculate averages
            avg_processing_times = {
                ptype: sum(times) / len(times) if times else 0
                for ptype, times in processing_times.items()
            }
            
            return {
                'last_hour_activity': activity_counts,
                'avg_processing_times_ms': avg_processing_times,
                'total_activities': sum(activity_counts.values()),
                'most_active_process': max(activity_counts.items(), key=lambda x: x[1])[0] if activity_counts else None,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get recent activity overview: {str(e)}")
            return {'error': str(e)}
    
    def _calculate_health_score(self, health_summary: Dict[str, Any], 
                              agent_summary: Any) -> float:
        """Calculate overall system health score (0-100)."""
        try:
            score = 100.0
            
            # Deduct for error rate
            error_rate = health_summary.get('error_rate_percent', 0)
            score -= min(error_rate * 2, 30)  # Max 30 point deduction
            
            # Deduct for slow processing
            avg_time = health_summary.get('avg_processing_time_ms', 0)
            if avg_time > 5000:  # 5 seconds
                score -= min((avg_time - 5000) / 1000 * 5, 20)  # Max 20 point deduction
            
            # Deduct for unhealthy agents
            if agent_summary.total_agents > 0:
                agent_health_ratio = agent_summary.healthy_agents / agent_summary.total_agents
                score -= (1 - agent_health_ratio) * 30  # Max 30 point deduction
            
            # Deduct for critical alerts
            score -= min(agent_summary.critical_alerts * 10, 20)  # Max 20 point deduction
            
            return max(score, 0.0)
            
        except Exception as e:
            self.logger.error(f"Failed to calculate health score: {str(e)}")
            return 50.0  # Default middle score
    
    def _get_health_status(self, health_score: float) -> str:
        """Get health status string based on score."""
        if health_score >= 90:
            return "Excellent"
        elif health_score >= 75:
            return "Good"
        elif health_score >= 60:
            return "Fair"
        elif health_score >= 40:
            return "Poor"
        else:
            return "Critical"
    
    def get_dashboard_json(self) -> str:
        """Get dashboard data as JSON string."""
        try:
            dashboard_data = self.get_dashboard_data()
            return json.dumps(asdict(dashboard_data), indent=2, default=str)
            
        except Exception as e:
            self.logger.error(f"Failed to get dashboard JSON: {str(e)}")
            return json.dumps({'error': str(e), 'timestamp': datetime.now().isoformat()})
    
    def get_summary_report(self) -> str:
        """Get a text summary report of system status."""
        try:
            dashboard_data = self.get_dashboard_data()
            
            report_lines = [
                "=== Smart Bug Triage System Status Report ===",
                f"Generated: {dashboard_data.timestamp}",
                "",
                "SYSTEM HEALTH:",
                f"  Overall Score: {dashboard_data.system_health.get('overall_health_score', 0):.1f}/100",
                f"  Status: {dashboard_data.system_health.get('status', 'Unknown')}",
                f"  Error Rate: {dashboard_data.system_health.get('error_rate_percent', 0):.1f}%",
                f"  Avg Processing Time: {dashboard_data.system_health.get('avg_processing_time_ms', 0):.0f}ms",
                "",
                "AGENTS:",
                f"  Total: {dashboard_data.agent_status.get('total_agents', 0)}",
                f"  Healthy: {dashboard_data.agent_status.get('healthy_agents', 0)}",
                f"  Health Percentage: {dashboard_data.agent_status.get('health_percentage', 0):.1f}%",
                "",
                "ACCURACY:",
                f"  Overall: {dashboard_data.accuracy_metrics.get('overall_accuracy', 0):.1%}",
                f"  Total Assignments: {dashboard_data.accuracy_metrics.get('total_assignments', 0)}",
                f"  Reassignment Rate: {dashboard_data.accuracy_metrics.get('reassignment_rate', 0):.1f}%",
                "",
                "ALERTS:",
                f"  Active Alerts: {len(dashboard_data.active_alerts)}",
                f"  Critical Alerts: {dashboard_data.system_health.get('critical_alerts', 0)}",
                ""
            ]
            
            # Add active alerts if any
            if dashboard_data.active_alerts:
                report_lines.append("ACTIVE ALERTS:")
                for alert in dashboard_data.active_alerts[:5]:  # Show top 5
                    report_lines.append(f"  [{alert['severity'].upper()}] {alert['alert_name']}: {alert['message']}")
                report_lines.append("")
            
            return "\n".join(report_lines)
            
        except Exception as e:
            self.logger.error(f"Failed to generate summary report: {str(e)}")
            return f"Error generating report: {str(e)}"
    
    def export_dashboard_data(self, filepath: str) -> bool:
        """Export dashboard data to a file."""
        try:
            dashboard_json = self.get_dashboard_json()
            
            with open(filepath, 'w') as f:
                f.write(dashboard_json)
            
            self.logger.info(f"Dashboard data exported to {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export dashboard data: {str(e)}")
            return False