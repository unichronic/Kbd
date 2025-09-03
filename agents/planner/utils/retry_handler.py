"""
Retry handling utilities for the Planner Agent.

This module provides robust retry mechanisms for handling
temporary failures in external service calls.
"""

import asyncio
import random
import time
from typing import Any, Callable, Optional, Type, Union
from functools import wraps


class RetryHandler:
    """Utility class for handling retries with various strategies."""
    
    @staticmethod
    def exponential_backoff(
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ):
        """
        Decorator for exponential backoff retry strategy.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            backoff_factor: Multiplier for delay after each retry
            jitter: Whether to add random jitter to delay
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = base_delay
                
                for attempt in range(max_retries + 1):
                    try:
                        if asyncio.iscoroutinefunction(func):
                            return await func(*args, **kwargs)
                        else:
                            return func(*args, **kwargs)
                            
                    except Exception as e:
                        last_exception = e
                        
                        if attempt < max_retries:
                            # Calculate delay with jitter
                            delay = current_delay
                            if jitter:
                                delay *= (0.5 + random.random() * 0.5)  # 50-100% of calculated delay
                            
                            delay = min(delay, max_delay)
                            
                            print(f"RetryHandler: Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                            await asyncio.sleep(delay)
                            current_delay *= backoff_factor
                        else:
                            print(f"RetryHandler: All {max_retries + 1} attempts failed. Last error: {e}")
                
                raise last_exception
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = base_delay
                
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                        
                    except Exception as e:
                        last_exception = e
                        
                        if attempt < max_retries:
                            # Calculate delay with jitter
                            delay = current_delay
                            if jitter:
                                delay *= (0.5 + random.random() * 0.5)
                            
                            delay = min(delay, max_delay)
                            
                            print(f"RetryHandler: Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                            time.sleep(delay)
                            current_delay *= backoff_factor
                        else:
                            print(f"RetryHandler: All {max_retries + 1} attempts failed. Last error: {e}")
                
                raise last_exception
            
            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator
    
    @staticmethod
    def linear_backoff(
        max_retries: int = 3,
        delay: float = 1.0,
        jitter: bool = True
    ):
        """
        Decorator for linear backoff retry strategy.
        
        Args:
            max_retries: Maximum number of retry attempts
            delay: Fixed delay in seconds
            jitter: Whether to add random jitter to delay
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries + 1):
                    try:
                        if asyncio.iscoroutinefunction(func):
                            return await func(*args, **kwargs)
                        else:
                            return func(*args, **kwargs)
                            
                    except Exception as e:
                        last_exception = e
                        
                        if attempt < max_retries:
                            # Calculate delay with jitter
                            actual_delay = delay
                            if jitter:
                                actual_delay *= (0.5 + random.random() * 0.5)
                            
                            print(f"RetryHandler: Attempt {attempt + 1} failed: {e}. Retrying in {actual_delay:.2f}s...")
                            await asyncio.sleep(actual_delay)
                        else:
                            print(f"RetryHandler: All {max_retries + 1} attempts failed. Last error: {e}")
                
                raise last_exception
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                        
                    except Exception as e:
                        last_exception = e
                        
                        if attempt < max_retries:
                            # Calculate delay with jitter
                            actual_delay = delay
                            if jitter:
                                actual_delay *= (0.5 + random.random() * 0.5)
                            
                            print(f"RetryHandler: Attempt {attempt + 1} failed: {e}. Retrying in {actual_delay:.2f}s...")
                            time.sleep(actual_delay)
                        else:
                            print(f"RetryHandler: All {max_retries + 1} attempts failed. Last error: {e}")
                
                raise last_exception
            
            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator
    
    @staticmethod
    def retry_on_exceptions(
        exceptions: Union[Type[Exception], tuple],
        max_retries: int = 3,
        delay: float = 1.0,
        backoff_factor: float = 2.0
    ):
        """
        Decorator for retrying on specific exceptions.
        
        Args:
            exceptions: Exception types to retry on
            max_retries: Maximum number of retry attempts
            delay: Initial delay in seconds
            backoff_factor: Multiplier for delay after each retry
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay
                
                for attempt in range(max_retries + 1):
                    try:
                        if asyncio.iscoroutinefunction(func):
                            return await func(*args, **kwargs)
                        else:
                            return func(*args, **kwargs)
                            
                    except exceptions as e:
                        last_exception = e
                        
                        if attempt < max_retries:
                            print(f"RetryHandler: Attempt {attempt + 1} failed with {type(e).__name__}: {e}. Retrying in {current_delay}s...")
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff_factor
                        else:
                            print(f"RetryHandler: All {max_retries + 1} attempts failed. Last error: {e}")
                            raise e
                    except Exception as e:
                        # Don't retry on other exceptions
                        print(f"RetryHandler: Non-retryable exception: {type(e).__name__}: {e}")
                        raise e
                
                raise last_exception
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay
                
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                        
                    except exceptions as e:
                        last_exception = e
                        
                        if attempt < max_retries:
                            print(f"RetryHandler: Attempt {attempt + 1} failed with {type(e).__name__}: {e}. Retrying in {current_delay}s...")
                            time.sleep(current_delay)
                            current_delay *= backoff_factor
                        else:
                            print(f"RetryHandler: All {max_retries + 1} attempts failed. Last error: {e}")
                            raise e
                    except Exception as e:
                        # Don't retry on other exceptions
                        print(f"RetryHandler: Non-retryable exception: {type(e).__name__}: {e}")
                        raise e
                
                raise last_exception
            
            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator
    
    @staticmethod
    async def execute_with_circuit_breaker(
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ) -> Any:
        """
        Execute a function with circuit breaker pattern.
        
        Args:
            func: Function to execute
            args: Function arguments
            kwargs: Function keyword arguments
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before trying again
            expected_exception: Exception type to count as failures
            
        Returns:
            Function result
        """
        if kwargs is None:
            kwargs = {}
        
        # Circuit breaker state (in a real implementation, this would be shared)
        circuit_state = {
            'failures': 0,
            'last_failure_time': None,
            'state': 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        }
        
        current_time = time.time()
        
        # Check if circuit is open
        if circuit_state['state'] == 'OPEN':
            if current_time - circuit_state['last_failure_time'] < recovery_timeout:
                raise Exception("Circuit breaker is OPEN - service unavailable")
            else:
                circuit_state['state'] = 'HALF_OPEN'
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Success - reset circuit breaker
            if circuit_state['state'] == 'HALF_OPEN':
                circuit_state['state'] = 'CLOSED'
            circuit_state['failures'] = 0
            
            return result
            
        except expected_exception as e:
            # Failure - update circuit breaker state
            circuit_state['failures'] += 1
            circuit_state['last_failure_time'] = current_time
            
            if circuit_state['failures'] >= failure_threshold:
                circuit_state['state'] = 'OPEN'
                print(f"RetryHandler: Circuit breaker opened after {failure_threshold} failures")
            
            raise e
