"""Health check server for container orchestration."""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn


class HealthStatus(Enum):
    """Health check status enumeration."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Individual health check result."""
    name: str
    status: HealthStatus
    message: str
    timestamp: datetime
    duration_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemHealth:
    """Overall system health status."""
    status: HealthStatus
    timestamp: datetime
    checks: List[HealthCheck]
    uptime_seconds: float
    version: str = "1.0.0"


class HealthServer:
    """HTTP server for health check endpoints."""
    
    def __init__(self, port: int = 8000, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self.app = FastAPI(title="Smart Bug Triage Health Check", version="1.0.0")
        self.logger = logging.getLogger(__name__)
        self.start_time = datetime.now()
        self.health_checks: Dict[str, Callable[[], HealthCheck]] = {}
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes for health checks."""
        
        @self.app.get("/health")
        async def health():
            """Main health check endpoint."""
            return await self._perform_health_checks()
        
        @self.app.get("/health/live")
        async def liveness():
            """Kubernetes liveness probe endpoint."""
            return {"status": "alive", "timestamp": datetime.now().isoformat()}
        
        @self.app.get("/health/ready")
        async def readiness():
            """Kubernetes readiness probe endpoint."""
            health_result = await self._perform_health_checks()
            if health_result["status"] in ["healthy", "degraded"]:
                return health_result
            else:
                raise HTTPException(status_code=503, detail=health_result)
        
        @self.app.get("/health/startup")
        async def startup():
            """Kubernetes startup probe endpoint."""
            # Check if critical components are ready
            critical_checks = await self._perform_critical_checks()
            if all(check.status == HealthStatus.HEALTHY for check in critical_checks):
                return {"status": "ready", "timestamp": datetime.now().isoformat()}
            else:
                raise HTTPException(status_code=503, detail="Not ready")
        
        @self.app.get("/metrics")
        async def metrics():
            """Basic metrics endpoint."""
            uptime = (datetime.now() - self.start_time).total_seconds()
            return {
                "uptime_seconds": uptime,
                "start_time": self.start_time.isoformat(),
                "health_checks_count": len(self.health_checks),
                "timestamp": datetime.now().isoformat()
            }
    
    def add_health_check(self, name: str, check_func: Callable[[], HealthCheck]):
        """Add a health check function."""
        self.health_checks[name] = check_func
        self.logger.info(f"Added health check: {name}")
    
    async def _perform_health_checks(self) -> Dict[str, Any]:
        """Perform all registered health checks."""
        checks = []
        overall_status = HealthStatus.HEALTHY
        
        for name, check_func in self.health_checks.items():
            try:
                start_time = datetime.now()
                check_result = check_func()
                duration = (datetime.now() - start_time).total_seconds() * 1000
                check_result.duration_ms = duration
                checks.append(check_result)
                
                # Determine overall status
                if check_result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif check_result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                    
            except Exception as e:
                self.logger.error(f"Health check {name} failed: {e}")
                checks.append(HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check failed: {str(e)}",
                    timestamp=datetime.now()
                ))
                overall_status = HealthStatus.UNHEALTHY
        
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        system_health = SystemHealth(
            status=overall_status,
            timestamp=datetime.now(),
            checks=checks,
            uptime_seconds=uptime
        )
        
        return asdict(system_health)
    
    async def _perform_critical_checks(self) -> List[HealthCheck]:
        """Perform only critical health checks for startup probe."""
        critical_check_names = ["database", "message_queue"]
        critical_checks = []
        
        for name in critical_check_names:
            if name in self.health_checks:
                try:
                    check_result = self.health_checks[name]()
                    critical_checks.append(check_result)
                except Exception as e:
                    critical_checks.append(HealthCheck(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Critical check failed: {str(e)}",
                        timestamp=datetime.now()
                    ))
        
        return critical_checks
    
    def run(self):
        """Run the health check server."""
        self.logger.info(f"Starting health check server on {self.host}:{self.port}")
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False
        )
    
    async def run_async(self):
        """Run the health check server asynchronously."""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False
        )
        server = uvicorn.Server(config)
        await server.serve()


def create_health_server(port: int = 8000) -> HealthServer:
    """Factory function to create a health server."""
    return HealthServer(port=port)