"""
Parallel execution utilities for the Planner Agent.

This module provides utilities for executing context gathering
and other operations in parallel for improved performance.
"""

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed


class ParallelExecutor:
    """Utility class for parallel execution of operations."""
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize the parallel executor.
        
        Args:
            max_workers: Maximum number of worker threads
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def execute_async_tasks(
        self, 
        tasks: List[Tuple[Callable, tuple, dict]], 
        timeout: Optional[float] = None
    ) -> List[Any]:
        """
        Execute multiple async tasks in parallel.
        
        Args:
            tasks: List of (function, args, kwargs) tuples
            timeout: Optional timeout for all tasks
            
        Returns:
            List of results in the same order as input tasks
        """
        try:
            # Create coroutines for all tasks
            coroutines = []
            for func, args, kwargs in tasks:
                coroutine = func(*args, **kwargs)
                coroutines.append(coroutine)
            
            # Execute all tasks in parallel
            if timeout:
                results = await asyncio.wait_for(
                    asyncio.gather(*coroutines, return_exceptions=True),
                    timeout=timeout
                )
            else:
                results = await asyncio.gather(*coroutines, return_exceptions=True)
            
            return results
            
        except asyncio.TimeoutError:
            print(f"ParallelExecutor: Tasks timed out after {timeout} seconds")
            return [TimeoutError("Task timed out")] * len(tasks)
        except Exception as e:
            print(f"ParallelExecutor: Error executing async tasks: {e}")
            return [e] * len(tasks)
    
    def execute_sync_tasks(
        self, 
        tasks: List[Tuple[Callable, tuple, dict]], 
        timeout: Optional[float] = None
    ) -> List[Any]:
        """
        Execute multiple synchronous tasks in parallel using thread pool.
        
        Args:
            tasks: List of (function, args, kwargs) tuples
            timeout: Optional timeout for all tasks
            
        Returns:
            List of results in the same order as input tasks
        """
        try:
            # Submit all tasks to thread pool
            futures = []
            for func, args, kwargs in tasks:
                future = self.executor.submit(func, *args, **kwargs)
                futures.append(future)
            
            # Collect results
            results = []
            if timeout:
                # Use as_completed with timeout
                for future in as_completed(futures, timeout=timeout):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        results.append(e)
            else:
                # Wait for all futures to complete
                for future in futures:
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        results.append(e)
            
            return results
            
        except Exception as e:
            print(f"ParallelExecutor: Error executing sync tasks: {e}")
            return [e] * len(tasks)
    
    async def execute_with_retry(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        max_retries: int = 3,
        delay: float = 1.0,
        backoff_factor: float = 2.0
    ) -> Any:
        """
        Execute a function with retry logic.
        
        Args:
            func: Function to execute
            args: Function arguments
            kwargs: Function keyword arguments
            max_retries: Maximum number of retries
            delay: Initial delay between retries
            backoff_factor: Backoff factor for delay
            
        Returns:
            Function result or last exception
        """
        if kwargs is None:
            kwargs = {}
        
        last_exception = None
        current_delay = delay
        
        for attempt in range(max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    print(f"ParallelExecutor: Attempt {attempt + 1} failed: {e}. Retrying in {current_delay}s...")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor
                else:
                    print(f"ParallelExecutor: All {max_retries + 1} attempts failed. Last error: {e}")
        
        return last_exception
    
    def execute_batch_with_retry(
        self,
        tasks: List[Tuple[Callable, tuple, dict]],
        max_retries: int = 3,
        delay: float = 1.0,
        backoff_factor: float = 2.0
    ) -> List[Any]:
        """
        Execute a batch of tasks with retry logic.
        
        Args:
            tasks: List of (function, args, kwargs) tuples
            max_retries: Maximum number of retries per task
            delay: Initial delay between retries
            backoff_factor: Backoff factor for delay
            
        Returns:
            List of results
        """
        results = []
        
        for func, args, kwargs in tasks:
            result = self._execute_single_with_retry(
                func, args, kwargs, max_retries, delay, backoff_factor
            )
            results.append(result)
        
        return results
    
    def _execute_single_with_retry(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        max_retries: int,
        delay: float,
        backoff_factor: float
    ) -> Any:
        """Execute a single function with retry logic."""
        last_exception = None
        current_delay = delay
        
        for attempt in range(max_retries + 1):
            try:
                result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    print(f"ParallelExecutor: Attempt {attempt + 1} failed: {e}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff_factor
                else:
                    print(f"ParallelExecutor: All {max_retries + 1} attempts failed. Last error: {e}")
        
        return last_exception
    
    async def execute_with_timeout(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        timeout: float = 30.0
    ) -> Any:
        """
        Execute a function with timeout.
        
        Args:
            func: Function to execute
            args: Function arguments
            kwargs: Function keyword arguments
            timeout: Timeout in seconds
            
        Returns:
            Function result or timeout exception
        """
        if kwargs is None:
            kwargs = {}
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            else:
                # Run sync function in thread pool with timeout
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(self.executor, func, *args, **kwargs),
                    timeout=timeout
                )
            return result
            
        except asyncio.TimeoutError:
            print(f"ParallelExecutor: Function timed out after {timeout} seconds")
            return TimeoutError(f"Function timed out after {timeout} seconds")
        except Exception as e:
            print(f"ParallelExecutor: Function execution failed: {e}")
            return e
    
    def close(self):
        """Close the thread pool executor."""
        self.executor.shutdown(wait=True)
        print("ParallelExecutor: Thread pool executor closed")
