"""Health check implementations for various system components."""

import time
from datetime import datetime
from typing import Optional, Dict, Any

from .health_server import HealthCheck, HealthStatus
from smart_bug_triage.database.connection import DatabaseManager
from smart_bug_triage.message_queue.connection import MessageQueueManager
from smart_bug_triage.config.settings import SystemConfig


class DatabaseHealthCheck:
    """Health check for database connectivity."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def __call__(self) -> HealthCheck:
        """Perform database health check."""
        try:
            start_time = time.time()
            
            # Test basic connectivity
            is_healthy = self.db_manager.health_check()
            
            if is_healthy:
                # Test query performance
                query_time = time.time() - start_time
                
                if query_time > 5.0:  # 5 second threshold
                    return HealthCheck(
                        name="database",
                        status=HealthStatus.DEGRADED,
                        message=f"Database responding slowly ({query_time:.2f}s)",
                        timestamp=datetime.now(),
                        details={"query_time_seconds": query_time}
                    )
                else:
                    return HealthCheck(
                        name="database",
                        status=HealthStatus.HEALTHY,
                        message="Database connection healthy",
                        timestamp=datetime.now(),
                        details={"query_time_seconds": query_time}
                    )
            else:
                return HealthCheck(
                    name="database",
                    status=HealthStatus.UNHEALTHY,
                    message="Database connection failed",
                    timestamp=datetime.now()
                )
                
        except Exception as e:
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database health check error: {str(e)}",
                timestamp=datetime.now()
            )


class MessageQueueHealthCheck:
    """Health check for message queue connectivity."""
    
    def __init__(self, mq_manager: MessageQueueManager):
        self.mq_manager = mq_manager
    
    def __call__(self) -> HealthCheck:
        """Perform message queue health check."""
        try:
            start_time = time.time()
            
            # Test connection
            is_connected = self.mq_manager.is_connected()
            
            if is_connected:
                # Test queue operations
                connection_time = time.time() - start_time
                
                if connection_time > 3.0:  # 3 second threshold
                    return HealthCheck(
                        name="message_queue",
                        status=HealthStatus.DEGRADED,
                        message=f"Message queue responding slowly ({connection_time:.2f}s)",
                        timestamp=datetime.now(),
                        details={"connection_time_seconds": connection_time}
                    )
                else:
                    return HealthCheck(
                        name="message_queue",
                        status=HealthStatus.HEALTHY,
                        message="Message queue connection healthy",
                        timestamp=datetime.now(),
                        details={"connection_time_seconds": connection_time}
                    )
            else:
                return HealthCheck(
                    name="message_queue",
                    status=HealthStatus.UNHEALTHY,
                    message="Message queue connection failed",
                    timestamp=datetime.now()
                )
                
        except Exception as e:
            return HealthCheck(
                name="message_queue",
                status=HealthStatus.UNHEALTHY,
                message=f"Message queue health check error: {str(e)}",
                timestamp=datetime.now()
            )


class APIHealthCheck:
    """Health check for external API connectivity."""
    
    def __init__(self, api_name: str, test_func: callable):
        self.api_name = api_name
        self.test_func = test_func
    
    def __call__(self) -> HealthCheck:
        """Perform API health check."""
        try:
            start_time = time.time()
            
            # Test API connectivity
            is_available = self.test_func()
            api_time = time.time() - start_time
            
            if is_available:
                if api_time > 10.0:  # 10 second threshold for external APIs
                    return HealthCheck(
                        name=f"api_{self.api_name}",
                        status=HealthStatus.DEGRADED,
                        message=f"{self.api_name} API responding slowly ({api_time:.2f}s)",
                        timestamp=datetime.now(),
                        details={"response_time_seconds": api_time}
                    )
                else:
                    return HealthCheck(
                        name=f"api_{self.api_name}",
                        status=HealthStatus.HEALTHY,
                        message=f"{self.api_name} API healthy",
                        timestamp=datetime.now(),
                        details={"response_time_seconds": api_time}
                    )
            else:
                return HealthCheck(
                    name=f"api_{self.api_name}",
                    status=HealthStatus.UNHEALTHY,
                    message=f"{self.api_name} API unavailable",
                    timestamp=datetime.now()
                )
                
        except Exception as e:
            return HealthCheck(
                name=f"api_{self.api_name}",
                status=HealthStatus.UNHEALTHY,
                message=f"{self.api_name} API health check error: {str(e)}",
                timestamp=datetime.now()
            )


class AgentHealthCheck:
    """Health check for agent status."""
    
    def __init__(self, agent_name: str, agent_instance):
        self.agent_name = agent_name
        self.agent_instance = agent_instance
    
    def __call__(self) -> HealthCheck:
        """Perform agent health check."""
        try:
            # Check if agent is running and healthy
            if hasattr(self.agent_instance, 'is_healthy'):
                is_healthy = self.agent_instance.is_healthy()
            else:
                # Fallback to basic status check
                status = self.agent_instance.get_status()
                is_healthy = status.get('status') in ['running', 'healthy']
            
            if is_healthy:
                return HealthCheck(
                    name=f"agent_{self.agent_name}",
                    status=HealthStatus.HEALTHY,
                    message=f"{self.agent_name} agent healthy",
                    timestamp=datetime.now()
                )
            else:
                return HealthCheck(
                    name=f"agent_{self.agent_name}",
                    status=HealthStatus.UNHEALTHY,
                    message=f"{self.agent_name} agent unhealthy",
                    timestamp=datetime.now()
                )
                
        except Exception as e:
            return HealthCheck(
                name=f"agent_{self.agent_name}",
                status=HealthStatus.UNHEALTHY,
                message=f"{self.agent_name} agent health check error: {str(e)}",
                timestamp=datetime.now()
            )


class SystemResourceHealthCheck:
    """Health check for system resources (memory, disk, etc.)."""
    
    def __init__(self, memory_threshold_mb: int = 1000, disk_threshold_mb: int = 1000):
        self.memory_threshold_mb = memory_threshold_mb
        self.disk_threshold_mb = disk_threshold_mb
    
    def __call__(self) -> HealthCheck:
        """Perform system resource health check."""
        try:
            import psutil
            
            # Check memory usage
            memory = psutil.virtual_memory()
            memory_available_mb = memory.available / (1024 * 1024)
            
            # Check disk usage
            disk = psutil.disk_usage('/')
            disk_free_mb = disk.free / (1024 * 1024)
            
            details = {
                "memory_available_mb": round(memory_available_mb, 2),
                "memory_percent_used": memory.percent,
                "disk_free_mb": round(disk_free_mb, 2),
                "disk_percent_used": round((disk.used / disk.total) * 100, 2)
            }
            
            # Determine status
            if memory_available_mb < self.memory_threshold_mb:
                return HealthCheck(
                    name="system_resources",
                    status=HealthStatus.DEGRADED,
                    message=f"Low memory: {memory_available_mb:.0f}MB available",
                    timestamp=datetime.now(),
                    details=details
                )
            elif disk_free_mb < self.disk_threshold_mb:
                return HealthCheck(
                    name="system_resources",
                    status=HealthStatus.DEGRADED,
                    message=f"Low disk space: {disk_free_mb:.0f}MB free",
                    timestamp=datetime.now(),
                    details=details
                )
            else:
                return HealthCheck(
                    name="system_resources",
                    status=HealthStatus.HEALTHY,
                    message="System resources healthy",
                    timestamp=datetime.now(),
                    details=details
                )
                
        except ImportError:
            return HealthCheck(
                name="system_resources",
                status=HealthStatus.UNKNOWN,
                message="psutil not available for resource monitoring",
                timestamp=datetime.now()
            )
        except Exception as e:
            return HealthCheck(
                name="system_resources",
                status=HealthStatus.UNHEALTHY,
                message=f"System resource check error: {str(e)}",
                timestamp=datetime.now()
            )