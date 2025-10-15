"""Automated alerting system for system degradation."""

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from smart_bug_triage.database.connection import get_db_session
from smart_bug_triage.models.database import SystemAlert, SystemMetric, ProcessingMetrics
from smart_bug_triage.monitoring.metrics_collector import MetricsCollector
from smart_bug_triage.monitoring.performance_monitor import PerformanceMonitor
from smart_bug_triage.monitoring.accuracy_tracker import AccuracyTracker
from smart_bug_triage.utils.logging import get_logger


@dataclass
class AlertRule:
    """Definition of an alert rule."""
    name: str
    alert_type: str
    severity: str
    condition: Callable[[], bool]
    message_template: str
    cooldown_minutes: int = 30


@dataclass
class AlertNotification:
    """Alert notification details."""
    alert_name: str
    alert_type: str
    severity: str
    message: str
    triggered_at: datetime
    is_resolved: bool = False


class AlertSystem:
    """Automated alerting system for monitoring system health."""
    
    def __init__(self, metrics_collector: MetricsCollector, 
                 performance_monitor: PerformanceMonitor,
                 accuracy_tracker: AccuracyTracker):
        self.metrics_collector = metrics_collector
        self.performance_monitor = performance_monitor
        self.accuracy_tracker = accuracy_tracker
        self.logger = get_logger(__name__)
        
        # Alert rules registry
        self.alert_rules: Dict[str, AlertRule] = {}
        
        # Initialize default alert rules
        self._setup_default_alert_rules()
    
    def _setup_default_alert_rules(self) -> None:
        """Set up default system alert rules."""
        
        # High error rate alert
        self.add_alert_rule(
            name="high_error_rate",
            alert_type="performance",
            severity="high",
            condition=lambda: self._check_error_rate_threshold(10.0),  # 10% error rate
            message_template="System error rate is {error_rate:.1f}% (threshold: 10%)",
            cooldown_minutes=15
        )
        
        # Slow processing alert
        self.add_alert_rule(
            name="slow_processing",
            alert_type="performance", 
            severity="medium",
            condition=lambda: self._check_processing_time_threshold(10000),  # 10 seconds
            message_template="Average processing time is {avg_time:.0f}ms (threshold: 10000ms)",
            cooldown_minutes=30
        )
        
        # Low accuracy alert
        self.add_alert_rule(
            name="low_accuracy",
            alert_type="accuracy",
            severity="high",
            condition=lambda: self._check_accuracy_threshold(0.7),  # 70% accuracy
            message_template="System accuracy is {accuracy:.1%} (threshold: 70%)",
            cooldown_minutes=60
        )
        
        # Queue backup alert
        self.add_alert_rule(
            name="queue_backup",
            alert_type="capacity",
            severity="medium",
            condition=lambda: self._check_queue_depth_threshold(100),  # 100 messages
            message_template="Message queue depth is {queue_depth} (threshold: 100)",
            cooldown_minutes=10
        )
        
        # No processing activity alert
        self.add_alert_rule(
            name="no_activity",
            alert_type="health",
            severity="critical",
            condition=lambda: self._check_no_activity_threshold(60),  # 60 minutes
            message_template="No processing activity detected for {minutes} minutes",
            cooldown_minutes=30
        )
        
        # High memory usage alert (simulated)
        self.add_alert_rule(
            name="high_memory_usage",
            alert_type="performance",
            severity="medium",
            condition=lambda: self._check_memory_usage_threshold(80.0),  # 80% memory
            message_template="Memory usage is {memory_usage:.1f}% (threshold: 80%)",
            cooldown_minutes=20
        )
    
    def add_alert_rule(self, name: str, alert_type: str, severity: str,
                      condition: Callable[[], bool], message_template: str,
                      cooldown_minutes: int = 30) -> None:
        """Add a new alert rule."""
        alert_rule = AlertRule(
            name=name,
            alert_type=alert_type,
            severity=severity,
            condition=condition,
            message_template=message_template,
            cooldown_minutes=cooldown_minutes
        )
        
        self.alert_rules[name] = alert_rule
        self.logger.info(f"Added alert rule: {name}")
    
    def check_all_alerts(self) -> List[AlertNotification]:
        """Check all alert rules and trigger alerts as needed."""
        triggered_alerts = []
        
        for rule_name, rule in self.alert_rules.items():
            try:
                # Check if alert is in cooldown period
                if self._is_alert_in_cooldown(rule_name, rule.cooldown_minutes):
                    continue
                
                # Evaluate the condition
                if rule.condition():
                    # Trigger the alert
                    alert_notification = self._trigger_alert(rule)
                    if alert_notification:
                        triggered_alerts.append(alert_notification)
                else:
                    # Resolve the alert if it was active
                    self._resolve_alert(rule_name)
                    
            except Exception as e:
                self.logger.error(f"Error checking alert rule {rule_name}: {str(e)}")
        
        return triggered_alerts
    
    def _trigger_alert(self, rule: AlertRule) -> Optional[AlertNotification]:
        """Trigger an alert and store it in the database."""
        try:
            # Generate the alert message
            message = self._generate_alert_message(rule)
            
            with get_db_session() as session:
                # Check if alert already exists and is active
                existing_alert = session.query(SystemAlert).filter(
                    and_(
                        SystemAlert.alert_name == rule.name,
                        SystemAlert.is_active == True
                    )
                ).first()
                
                if existing_alert:
                    # Update existing alert
                    existing_alert.message = message
                    existing_alert.triggered_at = datetime.now()
                    alert_id = existing_alert.id
                else:
                    # Create new alert
                    new_alert = SystemAlert(
                        alert_name=rule.name,
                        alert_type=rule.alert_type,
                        severity=rule.severity,
                        message=message,
                        is_active=True
                    )
                    session.add(new_alert)
                    session.flush()
                    alert_id = new_alert.id
                
                session.commit()
                
                self.logger.warning(f"Alert triggered: {rule.name} - {message}")
                
                return AlertNotification(
                    alert_name=rule.name,
                    alert_type=rule.alert_type,
                    severity=rule.severity,
                    message=message,
                    triggered_at=datetime.now()
                )
                
        except Exception as e:
            self.logger.error(f"Failed to trigger alert {rule.name}: {str(e)}")
            return None
    
    def _resolve_alert(self, alert_name: str) -> None:
        """Resolve an active alert."""
        try:
            with get_db_session() as session:
                alert = session.query(SystemAlert).filter(
                    and_(
                        SystemAlert.alert_name == alert_name,
                        SystemAlert.is_active == True
                    )
                ).first()
                
                if alert:
                    alert.is_active = False
                    alert.resolved_at = datetime.now()
                    session.commit()
                    self.logger.info(f"Alert resolved: {alert_name}")
                    
        except Exception as e:
            self.logger.error(f"Failed to resolve alert {alert_name}: {str(e)}")
    
    def _is_alert_in_cooldown(self, alert_name: str, cooldown_minutes: int) -> bool:
        """Check if an alert is in cooldown period."""
        try:
            cooldown_threshold = datetime.now() - timedelta(minutes=cooldown_minutes)
            
            with get_db_session() as session:
                recent_alert = session.query(SystemAlert).filter(
                    and_(
                        SystemAlert.alert_name == alert_name,
                        SystemAlert.triggered_at >= cooldown_threshold
                    )
                ).first()
                
                return recent_alert is not None
                
        except Exception as e:
            self.logger.error(f"Failed to check cooldown for {alert_name}: {str(e)}")
            return False
    
    def _generate_alert_message(self, rule: AlertRule) -> str:
        """Generate alert message with current metric values."""
        try:
            # Get current values for message formatting
            context = {}
            
            if rule.name == "high_error_rate":
                context['error_rate'] = self._get_current_error_rate()
            elif rule.name == "slow_processing":
                context['avg_time'] = self._get_current_avg_processing_time()
            elif rule.name == "low_accuracy":
                context['accuracy'] = self._get_current_accuracy()
            elif rule.name == "queue_backup":
                context['queue_depth'] = self._get_current_queue_depth()
            elif rule.name == "no_activity":
                context['minutes'] = self._get_minutes_since_last_activity()
            elif rule.name == "high_memory_usage":
                context['memory_usage'] = self._get_current_memory_usage()
            
            return rule.message_template.format(**context)
            
        except Exception as e:
            self.logger.error(f"Failed to generate message for {rule.name}: {str(e)}")
            return f"Alert: {rule.name} - Unable to generate detailed message"
    
    # Alert condition check methods
    
    def _check_error_rate_threshold(self, threshold_percent: float) -> bool:
        """Check if error rate exceeds threshold."""
        error_rate = self._get_current_error_rate()
        return error_rate > threshold_percent
    
    def _check_processing_time_threshold(self, threshold_ms: int) -> bool:
        """Check if average processing time exceeds threshold."""
        avg_time = self._get_current_avg_processing_time()
        return avg_time > threshold_ms
    
    def _check_accuracy_threshold(self, threshold: float) -> bool:
        """Check if accuracy falls below threshold."""
        accuracy = self._get_current_accuracy()
        return accuracy < threshold
    
    def _check_queue_depth_threshold(self, threshold: int) -> bool:
        """Check if queue depth exceeds threshold."""
        queue_depth = self._get_current_queue_depth()
        return queue_depth > threshold
    
    def _check_no_activity_threshold(self, threshold_minutes: int) -> bool:
        """Check if no activity for specified minutes."""
        minutes_since_activity = self._get_minutes_since_last_activity()
        return minutes_since_activity > threshold_minutes
    
    def _check_memory_usage_threshold(self, threshold_percent: float) -> bool:
        """Check if memory usage exceeds threshold."""
        memory_usage = self._get_current_memory_usage()
        return memory_usage > threshold_percent
    
    # Metric retrieval methods
    
    def _get_current_error_rate(self) -> float:
        """Get current error rate percentage."""
        try:
            performance_summary = self.performance_monitor.get_system_performance_summary()
            total_processes = performance_summary.get('total_processes_24h', 0)
            total_errors = performance_summary.get('total_errors_24h', 0)
            
            if total_processes == 0:
                return 0.0
            
            return (total_errors / total_processes) * 100
            
        except Exception as e:
            self.logger.error(f"Failed to get error rate: {str(e)}")
            return 0.0
    
    def _get_current_avg_processing_time(self) -> float:
        """Get current average processing time in milliseconds."""
        try:
            metrics = self.performance_monitor.get_performance_metrics(hours=1)
            
            if not metrics:
                return 0.0
            
            # Get average across all process types
            total_duration = 0.0
            total_processes = 0
            
            for process_metrics in metrics.values():
                total_duration += process_metrics.avg_duration_ms * process_metrics.total_processes
                total_processes += process_metrics.total_processes
            
            return total_duration / total_processes if total_processes > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"Failed to get avg processing time: {str(e)}")
            return 0.0
    
    def _get_current_accuracy(self) -> float:
        """Get current system accuracy."""
        try:
            accuracy_report = self.accuracy_tracker.get_accuracy_report(days=7)
            return accuracy_report.overall_accuracy
            
        except Exception as e:
            self.logger.error(f"Failed to get accuracy: {str(e)}")
            return 1.0  # Default to high accuracy to avoid false alerts
    
    def _get_current_queue_depth(self) -> int:
        """Get current message queue depth."""
        try:
            # This would typically query the message queue system
            # For now, simulate based on recent processing metrics
            stats = self.metrics_collector.get_metric_stats('queue_depth_triage', 5)
            return int(stats.get('avg', 0))
            
        except Exception as e:
            self.logger.error(f"Failed to get queue depth: {str(e)}")
            return 0
    
    def _get_minutes_since_last_activity(self) -> int:
        """Get minutes since last processing activity."""
        try:
            with get_db_session() as session:
                last_activity = session.query(ProcessingMetrics.start_time).order_by(
                    ProcessingMetrics.start_time.desc()
                ).first()
                
                if last_activity:
                    time_diff = datetime.now() - last_activity[0]
                    return int(time_diff.total_seconds() / 60)
                else:
                    return 999  # No activity found
                    
        except Exception as e:
            self.logger.error(f"Failed to get last activity: {str(e)}")
            return 0
    
    def _get_current_memory_usage(self) -> float:
        """Get current memory usage percentage (simulated)."""
        try:
            # In a real implementation, this would query system metrics
            # For now, simulate based on processing load
            stats = self.metrics_collector.get_metric_stats('bug_processing_time_triage', 60)
            processing_load = stats.get('count', 0)
            
            # Simulate memory usage based on processing load
            base_usage = 30.0  # Base memory usage
            load_factor = min(processing_load * 2, 50)  # Max 50% additional
            
            return base_usage + load_factor
            
        except Exception as e:
            self.logger.error(f"Failed to get memory usage: {str(e)}")
            return 30.0  # Default safe value
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all currently active alerts."""
        try:
            with get_db_session() as session:
                active_alerts = session.query(SystemAlert).filter(
                    SystemAlert.is_active == True
                ).order_by(SystemAlert.triggered_at.desc()).all()
                
                return [
                    {
                        'id': alert.id,
                        'alert_name': alert.alert_name,
                        'alert_type': alert.alert_type,
                        'severity': alert.severity,
                        'message': alert.message,
                        'triggered_at': alert.triggered_at.isoformat(),
                        'acknowledged_at': alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
                    }
                    for alert in active_alerts
                ]
                
        except Exception as e:
            self.logger.error(f"Failed to get active alerts: {str(e)}")
            return []
    
    def acknowledge_alert(self, alert_id: int) -> bool:
        """Acknowledge an alert."""
        try:
            with get_db_session() as session:
                alert = session.query(SystemAlert).filter(
                    SystemAlert.id == alert_id
                ).first()
                
                if alert:
                    alert.acknowledged_at = datetime.now()
                    session.commit()
                    self.logger.info(f"Alert acknowledged: {alert.alert_name}")
                    return True
                else:
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to acknowledge alert {alert_id}: {str(e)}")
            return False
    
    def get_alert_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get alert history for the specified period."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with get_db_session() as session:
                alerts = session.query(SystemAlert).filter(
                    SystemAlert.triggered_at >= cutoff_date
                ).order_by(SystemAlert.triggered_at.desc()).all()
                
                return [
                    {
                        'id': alert.id,
                        'alert_name': alert.alert_name,
                        'alert_type': alert.alert_type,
                        'severity': alert.severity,
                        'message': alert.message,
                        'triggered_at': alert.triggered_at.isoformat(),
                        'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
                        'is_active': alert.is_active
                    }
                    for alert in alerts
                ]
                
        except Exception as e:
            self.logger.error(f"Failed to get alert history: {str(e)}")
            return []