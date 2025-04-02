#!/usr/bin/env python3
"""
Metrics collection and monitoring for the Shorpy Scraper application.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, TypeVar, cast
import functools

logger = logging.getLogger(__name__)

# Directory for metrics storage
METRICS_DIR = os.path.join(os.getcwd(), "metrics")
os.makedirs(METRICS_DIR, exist_ok=True)

# Type variable for generic function
T = TypeVar('T')

class Metrics:
    """Metrics collection and tracking for application monitoring."""
    
    def __init__(self, app_name: str = "shorpy_scraper"):
        """
        Initialize the metrics collector.
        
        Args:
            app_name: Name of the application for metrics labeling
        """
        self.app_name = app_name
        self.metrics_file = os.path.join(METRICS_DIR, f"{app_name}_metrics.json")
        self.counters: Dict[str, int] = {}
        self.timers: Dict[str, List[float]] = {}
        self.gauges: Dict[str, float] = {}
        self.load_metrics()
    
    def load_metrics(self) -> None:
        """Load existing metrics from file."""
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    self.counters = data.get('counters', {})
                    self.timers = data.get('timers', {})
                    self.gauges = data.get('gauges', {})
            except Exception as e:
                logger.error(f"Error loading metrics from {self.metrics_file}: {str(e)}")
    
    def save_metrics(self) -> None:
        """Save current metrics to file."""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump({
                    'counters': self.counters,
                    'timers': self.timers,
                    'gauges': self.gauges,
                    'updated_at': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving metrics to {self.metrics_file}: {str(e)}")
    
    def increment_counter(self, name: str, value: int = 1) -> None:
        """
        Increment a counter metric.
        
        Args:
            name: Name of the counter
            value: Value to increment by
        """
        if name not in self.counters:
            self.counters[name] = 0
        self.counters[name] += value
        self.save_metrics()
    
    def set_gauge(self, name: str, value: float) -> None:
        """
        Set a gauge metric.
        
        Args:
            name: Name of the gauge
            value: Value to set
        """
        self.gauges[name] = value
        self.save_metrics()
    
    def record_time(self, name: str, value: float) -> None:
        """
        Record a timing metric.
        
        Args:
            name: Name of the timer
            value: Time value to record in seconds
        """
        if name not in self.timers:
            self.timers[name] = []
        
        # Keep last 1000 timing values for statistics
        if len(self.timers[name]) >= 1000:
            self.timers[name].pop(0)
            
        self.timers[name].append(value)
        self.save_metrics()
    
    def get_counter(self, name: str) -> int:
        """
        Get the current value of a counter.
        
        Args:
            name: Name of the counter
            
        Returns:
            Current counter value
        """
        return self.counters.get(name, 0)
    
    def get_gauge(self, name: str) -> float:
        """
        Get the current value of a gauge.
        
        Args:
            name: Name of the gauge
            
        Returns:
            Current gauge value
        """
        return self.gauges.get(name, 0.0)
    
    def get_timer_stats(self, name: str) -> Dict[str, float]:
        """
        Get statistics for a timer.
        
        Args:
            name: Name of the timer
            
        Returns:
            Dictionary with timer statistics
        """
        if name not in self.timers or not self.timers[name]:
            return {
                'count': 0,
                'min': 0.0,
                'max': 0.0,
                'avg': 0.0,
                'p95': 0.0
            }
        
        values = self.timers[name]
        values_sorted = sorted(values)
        
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'p95': values_sorted[int(len(values_sorted) * 0.95)]
        }
    
    def get_daily_report(self) -> Dict[str, Any]:
        """
        Generate a daily metrics report.
        
        Returns:
            Dictionary with metrics report
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'counters': self.counters,
            'gauges': self.gauges,
            'timers': {name: self.get_timer_stats(name) for name in self.timers}
        }

def timed(metric_name: Optional[str] = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to time a function and record the duration as a metric.
    
    Args:
        metric_name: Name of the metric to record (defaults to function name)
        
    Returns:
        Decorated function that records timing metrics
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            name = metric_name or f"{func.__module__}.{func.__name__}"
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                metrics.record_time(name, duration)
        
        return wrapper
    return decorator

def counted(metric_name: Optional[str] = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to count function calls.
    
    Args:
        metric_name: Name of the counter (defaults to function name)
        
    Returns:
        Decorated function that counts invocations
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            name = metric_name or f"{func.__module__}.{func.__name__}.calls"
            metrics.increment_counter(name)
            return func(*args, **kwargs)
        
        return wrapper
    return decorator

# Create a singleton instance
metrics = Metrics() 