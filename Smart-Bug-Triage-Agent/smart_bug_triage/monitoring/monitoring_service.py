"""Main monitoring service that coordinates all monitoring components."""

import threading
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from smart_bug_triage.monitoring.metrics_collector import MetricsCollector, SystemMetricsCollector
from smart_bug_triage.monitoring.accuracy_tracker import AccuracyTracker
from smart_bug_triage.monitoring.agent_monitor import AgentHealthMonitor
from smart_bug_triage.monitoring.performance_monitor import PerformanceMonitor
from smart_bug_triage.monitoring.alert_system import AlertSystem
from smart_bug_triage.monitoring.dashboard import MetricsDashboard
from smart_bug_triage.utils.logging import get_logger


class MonitoringService:
    """Main monitoring service that coordinates all monitoring components."""
    
    def __init__(self, check_interval_seconds: int = 300):  # 5 minutes default
        self.logger = get_logger(__name__)
        self.check_interval = check_interval_seconds
        self.is_running = False
        self.monitoring_thread: Optional[threading.Thread] = None
        
        # Initialize monitoring components
        self.metrics_collector = MetricsCollector()
        self.system_metrics = SystemMetricsCollector(self.metrics_collector)
        self.accuracy_tracker = AccuracyTracker()
        self.agent_monitor = AgentHealthMonitor()
        self.performance_monitor = PerformanceMonitor()
        self.alert_system = AlertSystem(
            self.metrics_collector,
            self.performance_monitor,
            self.accuracy_tracker
        )
        self.dashboard = MetricsDashboard(
            self.metrics_collector,
            self.system_metrics,
            self.accuracy_tracker,
            self.agent_monitor,
            self.performance_monitor,
            self.alert_system
        )
        
        self.logger.info("Monitoring service initialized")
    
    def start(self) -> None:
        """Start the monitoring service."""
        if self.is_running:
            self.logger.warning("Monitoring service is already running")
            return
        
        self.is_running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        self.logger.info("Monitoring service started")
    
    def stop(self) -> None:
        """Stop the monitoring service."""
        if not self.is_running:
            self.logger.warning("Monitoring service is not running")
            return
        
        self.is_running = False
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=10)
        
        # Flush any remaining metrics
        self.metrics_collector.flush_metrics()
        
        self.logger.info("Monitoring service stopped")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs periodic checks."""
        self.logger.info("Monitoring loop started")
        
        while self.is_running:
            try:
                start_time = time.time()
                
                # Perform monitoring tasks
                self._perform_monitoring_cycle()
                
                # Calculate how long the cycle took
                cycle_duration = time.time() - start_time
                self.metrics_collector.record_timer(
                    'monitoring_cycle_duration',
                    cycle_duration * 1000,  # Convert to milliseconds
                    {'cycle_type': 'full'}
                )
                
                # Sleep for the remaining interval time
                sleep_time = max(0, self.check_interval - cycle_duration)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    self.logger.warning(
                        f"Monitoring cycle took {cycle_duration:.2f}s, "
                        f"longer than interval {self.check_interval}s"
                    )
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {str(e)}")
                time.sleep(60)  # Wait 1 minute before retrying
        
        self.logger.info("Monitoring loop stopped")
    
    def _perform_monitoring_cycle(self) -> None:
        """Perform one complete monitoring cycle."""
        try:
            # 1. Check agent health and create alerts for unhealthy agents
            self.logger.debug("Checking agent health")
            unhealthy_agents = self.agent_monitor.check_agent_health_and_alert()
            if unhealthy_agents:
                self.logger.warning(f"Found {len(unhealthy_agents)} unhealthy agents")
            
            # 2. Check all alert rules
            self.logger.debug("Checking alert rules")
            triggered_alerts = self.alert_system.check_all_alerts()
            if triggered_alerts:
                self.logger.warning(f"Triggered {len(triggered_alerts)} alerts")
                for alert in triggered_alerts:
                    self.logger.warning(f"Alert: {alert.alert_name} - {alert.message}")
            
            # 3. Flush metrics to database
            self.logger.debug("Flushing metrics")
            self.metrics_collector.flush_metrics()
            
            # 4. Record monitoring cycle metrics
            self.metrics_collector.record_counter('monitoring_cycles_completed', 1.0)
            
            # 5. Log system health summary
            if self.logger.isEnabledFor(10):  # DEBUG level
                health_summary = self.system_metrics.get_system_health_summary()
                self.logger.debug(f"System health: {health_summary}")
            
        except Exception as e:
            self.logger.error(f"Error in monitoring cycle: {str(e)}")
            self.metrics_collector.record_counter('monitoring_cycle_errors', 1.0)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status."""
        try:
            dashboard_data = self.dashboard.get_dashboard_data()
            
            return {
                'monitoring_service': {
                    'is_running': self.is_running,
                    'check_interval_seconds': self.check_interval,
                    'last_check': datetime.now().isoformat()
                },
                'system_health': dashboard_data.system_health,
                'active_alerts_count': len(dashboard_data.active_alerts),
                'critical_alerts': [
                    alert for alert in dashboard_data.active_alerts
                    if alert['severity'] == 'critical'
                ],
                'timestamp': dashboard_data.timestamp
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get system status: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        try:
            return self.performance_monitor.get_system_performance_summary()
        except Exception as e:
            self.logger.error(f"Failed to get performance summary: {str(e)}")
            return {'error': str(e)}
    
    def get_accuracy_summary(self) -> Dict[str, Any]:
        """Get accuracy summary."""
        try:
            report = self.accuracy_tracker.get_accuracy_report(days=7)
            return {
                'overall_accuracy': report.overall_accuracy,
                'total_assignments': report.total_assignments,
                'feedback_count': report.feedback_count,
                'avg_resolution_time': report.avg_resolution_time,
                'reassignment_rate': report.reassignment_rate,
                'time_period': report.time_period
            }
        except Exception as e:
            self.logger.error(f"Failed to get accuracy summary: {str(e)}")
            return {'error': str(e)}
    
    def get_agent_summary(self) -> Dict[str, Any]:
        """Get agent health summary."""
        try:
            summary = self.agent_monitor.get_system_health_summary()
            return {
                'total_agents': summary.total_agents,
                'healthy_agents': summary.healthy_agents,
                'unhealthy_agents': summary.unhealthy_agents,
                'agents_by_type': summary.agents_by_type,
                'avg_uptime_percentage': summary.avg_uptime_percentage,
                'last_updated': summary.last_updated.isoformat()
            }
        except Exception as e:
            self.logger.error(f"Failed to get agent summary: {str(e)}")
            return {'error': str(e)}
    
    def record_bug_processing(self, bug_id: str, process_type: str, 
                            start_time: datetime, success: bool = True,
                            error_message: Optional[str] = None) -> None:
        """Record bug processing metrics."""
        try:
            self.system_metrics.record_bug_processing_time(
                bug_id, process_type, start_time, success, error_message
            )
        except Exception as e:
            self.logger.error(f"Failed to record bug processing: {str(e)}")
    
    def record_assignment(self, assignment_id: str, developer_count: int,
                         confidence_score: float) -> None:
        """Record assignment metrics."""
        try:
            self.system_metrics.record_assignment_metrics(
                assignment_id, developer_count, confidence_score
            )
        except Exception as e:
            self.logger.error(f"Failed to record assignment: {str(e)}")
    
    def record_agent_heartbeat(self, agent_id: str, agent_type: str,
                             status: str = 'active', 
                             error_message: Optional[str] = None) -> None:
        """Record agent heartbeat."""
        try:
            self.agent_monitor.record_agent_heartbeat(
                agent_id, agent_type, status, None, error_message
            )
            self.system_metrics.record_agent_heartbeat(agent_id, agent_type)
        except Exception as e:
            self.logger.error(f"Failed to record agent heartbeat: {str(e)}")
    
    def record_assignment_accuracy(self, assignment_id: str, 
                                 predicted_category, predicted_developer: str,
                                 actual_category=None, feedback_rating: Optional[int] = None,
                                 resolution_time_minutes: Optional[int] = None,
                                 was_reassigned: bool = False) -> None:
        """Record assignment accuracy."""
        try:
            self.accuracy_tracker.record_assignment_accuracy(
                assignment_id, predicted_category, predicted_developer,
                actual_category, feedback_rating, resolution_time_minutes,
                was_reassigned
            )
        except Exception as e:
            self.logger.error(f"Failed to record assignment accuracy: {str(e)}")
    
    def update_accuracy_from_feedback(self, assignment_id: str) -> None:
        """Update accuracy when feedback is received."""
        try:
            self.accuracy_tracker.update_accuracy_from_feedback(assignment_id)
        except Exception as e:
            self.logger.error(f"Failed to update accuracy from feedback: {str(e)}")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get complete dashboard data."""
        try:
            dashboard_data = self.dashboard.get_dashboard_data()
            return {
                'system_health': dashboard_data.system_health,
                'performance_metrics': dashboard_data.performance_metrics,
                'accuracy_metrics': dashboard_data.accuracy_metrics,
                'agent_status': dashboard_data.agent_status,
                'active_alerts': dashboard_data.active_alerts,
                'recent_activity': dashboard_data.recent_activity,
                'timestamp': dashboard_data.timestamp
            }
        except Exception as e:
            self.logger.error(f"Failed to get dashboard data: {str(e)}")
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}
    
    def export_dashboard(self, filepath: str) -> bool:
        """Export dashboard data to file."""
        try:
            return self.dashboard.export_dashboard_data(filepath)
        except Exception as e:
            self.logger.error(f"Failed to export dashboard: {str(e)}")
            return False
    
    def get_summary_report(self) -> str:
        """Get text summary report."""
        try:
            return self.dashboard.get_summary_report()
        except Exception as e:
            self.logger.error(f"Failed to get summary report: {str(e)}")
            return f"Error generating report: {str(e)}"
    
    def acknowledge_alert(self, alert_id: int) -> bool:
        """Acknowledge an alert."""
        try:
            return self.alert_system.acknowledge_alert(alert_id)
        except Exception as e:
            self.logger.error(f"Failed to acknowledge alert: {str(e)}")
            return False
    
    def get_active_alerts(self) -> list:
        """Get active alerts."""
        try:
            return self.alert_system.get_active_alerts()
        except Exception as e:
            self.logger.error(f"Failed to get active alerts: {str(e)}")
            return []
    
    def is_healthy(self) -> bool:
        """Check if the monitoring service itself is healthy."""
        try:
            # Check if monitoring thread is running
            if not self.is_running:
                return False
            
            if not self.monitoring_thread or not self.monitoring_thread.is_alive():
                return False
            
            # Check if we can get basic system status
            status = self.get_system_status()
            if 'error' in status:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
            return False


# Global monitoring service instance
monitoring_service = MonitoringService()