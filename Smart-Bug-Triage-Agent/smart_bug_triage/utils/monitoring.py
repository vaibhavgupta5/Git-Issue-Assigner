"""Monitoring and metrics utilities."""

import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading
from smart_bug_triage.utils.logging import get_logger


@dataclass
class MetricValue:
    """A single metric measurement."""
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Collects and stores system metrics."""
    
    def __init__(self, retention_hours: int = 24):
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque())
        self.retention_hours = retention_hours
        self.lock = threading.Lock()
        self.logger = get_logger(__name__)
    
    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a metric value."""
        metric = MetricValue(
            value=value,
            timestamp=datetime.now(),
            tags=tags or {}
        )
        
        with self.lock:
            self.metrics[name].append(metric)
            self._cleanup_old_metrics(name)
    
    def _cleanup_old_metrics(self, metric_name: str) -> None:
        """Remove metrics older than retention period."""
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
        metrics_queue = self.metrics[metric_name]
        
        while metrics_queue and metrics_queue[0].timestamp < cutoff_time:
            metrics_queue.popleft()
    
    def get_metric_stats(self, name: str, window_minutes: int = 60) -> Dict[str, float]:
        """Get statistics for a metric within a time window."""
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        
        with self.lock:
            recent_values = [
                m.value for m in self.metrics[name]
                if m.timestamp >= cutoff_time
            ]
        
        if not recent_values:
            return {"count": 0, "avg": 0, "min": 0, "max": 0, "sum": 0}
        
        return {
            "count": len(recent_values),
            "avg": sum(recent_values) / len(recent_values),
            "min": min(recent_values),
            "max": max(recent_values),
            "sum": sum(recent_values)
        }
    
    def get_all_metrics_summary(self) -> Dict[str, Dict[str, float]]:
        """Get summary statistics for all metrics."""
        summary = {}
        with self.lock:
            for metric_name in self.metrics.keys():
                summary[metric_name] = self.get_metric_stats(metric_name)
        return summary


class PerformanceTimer:
    """Context manager for timing operations."""
    
    def __init__(self, metrics_collector: MetricsCollector, metric_name: str, 
                 tags: Optional[Dict[str, str]] = None):
        self.metrics_collector = metrics_collector
        self.metric_name = metric_name
        self.tags = tags or {}
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.time() - self.start_time
            self.metrics_collector.record_metric(
                self.metric_name, 
                duration * 1000,  # Convert to milliseconds
                self.tags
            )


class HealthChecker:
    """System health monitoring."""
    
    def __init__(self):
        self.health_checks: Dict[str, Callable[[], bool]] = {}
        self.logger = get_logger(__name__)
    
    def register_health_check(self, name: str, check_func: Callable[[], bool]) -> None:
        """Register a health check function."""
        self.health_checks[name] = check_func
        self.logger.info(f"Registered health check: {name}")
    
    def run_health_checks(self) -> Dict[str, Dict[str, Any]]:
        """Run all registered health checks."""
        results = {}
        
        for name, check_func in self.health_checks.items():
            try:
                start_time = time.time()
                is_healthy = check_func()
                duration = time.time() - start_time
                
                results[name] = {
                    "healthy": is_healthy,
                    "duration_ms": duration * 1000,
                    "timestamp": datetime.now().isoformat(),
                    "error": None
                }
                
            except Exception as e:
                self.logger.error(f"Health check {name} failed: {str(e)}")
                results[name] = {
                    "healthy": False,
                    "duration_ms": 0,
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                }
        
        return results
    
    def is_system_healthy(self) -> bool:
        """Check if the overall system is healthy."""
        results = self.run_health_checks()
        return all(result["healthy"] for result in results.values())


class AlertManager:
    """Manages system alerts and notifications."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.alert_rules: Dict[str, Dict[str, Any]] = {}
        self.active_alerts: Dict[str, datetime] = {}
        self.logger = get_logger(__name__)
    
    def add_alert_rule(self, name: str, metric_name: str, threshold: float, 
                      comparison: str = "greater", window_minutes: int = 5) -> None:
        """Add an alert rule for a metric."""
        self.alert_rules[name] = {
            "metric_name": metric_name,
            "threshold": threshold,
            "comparison": comparison,
            "window_minutes": window_minutes
        }
        self.logger.info(f"Added alert rule: {name}")
    
    def check_alerts(self) -> Dict[str, bool]:
        """Check all alert rules and return active alerts."""
        active_alerts = {}
        
        for alert_name, rule in self.alert_rules.items():
            stats = self.metrics_collector.get_metric_stats(
                rule["metric_name"], 
                rule["window_minutes"]
            )
            
            if stats["count"] == 0:
                continue
            
            value = stats["avg"]
            threshold = rule["threshold"]
            comparison = rule["comparison"]
            
            is_triggered = False
            if comparison == "greater":
                is_triggered = value > threshold
            elif comparison == "less":
                is_triggered = value < threshold
            elif comparison == "equal":
                is_triggered = abs(value - threshold) < 0.001
            
            if is_triggered:
                if alert_name not in self.active_alerts:
                    self.active_alerts[alert_name] = datetime.now()
                    self.logger.warning(f"Alert triggered: {alert_name} - {value} {comparison} {threshold}")
                active_alerts[alert_name] = True
            else:
                if alert_name in self.active_alerts:
                    del self.active_alerts[alert_name]
                    self.logger.info(f"Alert resolved: {alert_name}")
                active_alerts[alert_name] = False
        
        return active_alerts


# Global instances
metrics_collector = MetricsCollector()
health_checker = HealthChecker()
alert_manager = AlertManager(metrics_collector)