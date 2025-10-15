"""Base API client with common functionality."""

import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_window: int
    window_seconds: int
    burst_limit: int = 10


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    expected_exception: type = requests.RequestException


class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.requests_per_window
        self.last_refill = time.time()
        self.logger = logging.getLogger(__name__)
    
    def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens from the bucket."""
        now = time.time()
        
        # Refill tokens based on elapsed time
        elapsed = now - self.last_refill
        tokens_to_add = int(elapsed * (self.config.requests_per_window / self.config.window_seconds))
        
        if tokens_to_add > 0:
            self.tokens = min(self.config.requests_per_window, self.tokens + tokens_to_add)
            self.last_refill = now
        
        # Check if we have enough tokens
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        return False
    
    def wait_time(self) -> float:
        """Calculate wait time until next token is available."""
        if self.tokens >= 1:
            return 0.0
        
        tokens_needed = 1 - self.tokens
        return tokens_needed * (self.config.window_seconds / self.config.requests_per_window)


class CircuitBreaker:
    """Circuit breaker pattern implementation."""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.logger = logging.getLogger(__name__)
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == CircuitBreakerState.OPEN:
            if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.expected_exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Handle successful call."""
        self.failure_count = 0
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            self.logger.info("Circuit breaker transitioning to CLOSED")
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.logger.warning(f"Circuit breaker transitioning to OPEN after {self.failure_count} failures")


class BaseAPIClient(ABC):
    """Base class for API clients with common functionality."""
    
    def __init__(
        self,
        base_url: str,
        rate_limit_config: RateLimitConfig,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Set up rate limiting
        self.rate_limiter = RateLimiter(rate_limit_config)
        
        # Set up circuit breaker
        if circuit_breaker_config:
            self.circuit_breaker = CircuitBreaker(circuit_breaker_config)
        else:
            self.circuit_breaker = None
        
        # Set up requests session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    @abstractmethod
    def authenticate(self) -> Dict[str, str]:
        """Return authentication headers."""
        pass
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        """Make HTTP request with rate limiting and circuit breaker."""
        # Wait for rate limit
        while not self.rate_limiter.acquire():
            wait_time = self.rate_limiter.wait_time()
            self.logger.info(f"Rate limit reached, waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
        
        # Prepare request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_headers = self.authenticate()
        if headers:
            request_headers.update(headers)
        
        # Make request with circuit breaker protection
        def _request():
            return self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json_data,
                headers=request_headers,
                timeout=self.timeout
            )
        
        if self.circuit_breaker:
            response = self.circuit_breaker.call(_request)
        else:
            response = _request()
        
        # Log request details
        self.logger.debug(f"{method} {url} -> {response.status_code}")
        
        # Raise for HTTP errors
        response.raise_for_status()
        
        return response
    
    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """Make GET request."""
        return self._make_request("GET", endpoint, params=params)
    
    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """Make POST request."""
        return self._make_request("POST", endpoint, data=data, json_data=json_data)
    
    def put(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """Make PUT request."""
        return self._make_request("PUT", endpoint, data=data, json_data=json_data)
    
    def patch(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """Make PATCH request."""
        return self._make_request("PATCH", endpoint, data=data, json_data=json_data)
    
    def delete(self, endpoint: str) -> requests.Response:
        """Make DELETE request."""
        return self._make_request("DELETE", endpoint)