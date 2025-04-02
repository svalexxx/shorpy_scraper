#!/usr/bin/env python3
"""
Error handling utilities for the Shorpy Scraper application.
"""

import functools
import logging
import time
import traceback
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError,
)

logger = logging.getLogger(__name__)

# Type variable for generic function
T = TypeVar('T')

def with_retry(
    max_attempts: int = 3,
    retry_on_exceptions: tuple = (Exception,),
    exclude_exceptions: tuple = (),
    base_wait_seconds: float = 1.0,
    max_wait_seconds: float = 10.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        retry_on_exceptions: Tuple of exceptions to retry on
        exclude_exceptions: Tuple of exceptions to not retry on
        base_wait_seconds: Initial wait time between retries
        max_wait_seconds: Maximum wait time between retries
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            @retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=base_wait_seconds, max=max_wait_seconds),
                retry=retry_if_exception_type(retry_on_exceptions),
                reraise=True,
            )
            def _retry_wrapper() -> T:
                try:
                    return func(*args, **kwargs)
                except exclude_exceptions:
                    # Don't retry these exceptions
                    raise
                except Exception as e:
                    logger.warning(
                        f"Retrying {func.__name__} due to {e.__class__.__name__}: {str(e)}"
                    )
                    raise
            
            try:
                return _retry_wrapper()
            except RetryError as e:
                logger.error(
                    f"Function {func.__name__} failed after {max_attempts} attempts: {str(e)}"
                )
                if e.last_attempt.exception():
                    raise e.last_attempt.exception()
                raise
            
        return wrapper
    return decorator

def safe_execute(
    default_return: Optional[Any] = None,
    log_exception: bool = True,
) -> Callable[[Callable[..., T]], Callable[..., Optional[T]]]:
    """
    Decorator to safely execute a function and handle exceptions.
    
    Args:
        default_return: Value to return if an exception occurs
        log_exception: Whether to log the exception
        
    Returns:
        Decorated function that handles exceptions
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_exception:
                    logger.error(
                        f"Exception in {func.__name__}: {e.__class__.__name__}: {str(e)}\n"
                        f"{traceback.format_exc()}"
                    )
                return default_return
        
        return wrapper
    return decorator

def create_error_context(
    operation: str,
    extra_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a context dictionary for error logging.
    
    Args:
        operation: Name of the operation being performed
        extra_info: Additional information to include in the context
        
    Returns:
        Dictionary with error context information
    """
    context = {
        "operation": operation,
        "timestamp": time.time(),
    }
    
    if extra_info:
        context.update(extra_info)
        
    return context 