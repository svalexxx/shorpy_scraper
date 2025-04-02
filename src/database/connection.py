#!/usr/bin/env python3
"""
Database connection management with connection pooling.
"""

import sqlite3
import logging
import os
import threading
import time
from typing import Dict, Any, List, Optional, Union
from contextlib import contextmanager

from src.config import config
from src.utils.error_handler import with_retry

# Set up logger
logger = logging.getLogger(__name__)

class DBConnectionPool:
    """Connection pool for SQLite database with thread safety."""
    
    def __init__(self, db_path: Optional[str] = None, max_connections: int = 10, timeout: float = 20.0):
        """
        Initialize the SQLite connection pool.
        
        Args:
            db_path: Path to SQLite database file
            max_connections: Maximum number of connections in the pool
            timeout: Connection timeout in seconds
        """
        self.db_path = db_path or config.get("db_path", "shorpy_data.db")
        self.max_connections = max_connections
        self.timeout = timeout
        
        # Create parent directory if it doesn't exist
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        # Thread-local storage for connections
        self._thread_local = threading.local()
        
        # Pool of available connections
        self._connections = []
        self._connections_lock = threading.RLock()
        
        # Connection metadata
        self._connection_usage: Dict[int, Dict[str, Any]] = {}
        
        logger.info(f"Initialized database connection pool with path: {self.db_path}")
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection."""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Track connection creation time and usage count
        conn_id = id(conn)
        self._connection_usage[conn_id] = {
            "created_at": time.time(),
            "last_used": time.time(),
            "use_count": 0
        }
        
        return conn
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool or create a new one if needed."""
        if hasattr(self._thread_local, "connection"):
            # If thread already has a connection, reuse it
            conn = self._thread_local.connection
            self._connection_usage[id(conn)]["use_count"] += 1
            self._connection_usage[id(conn)]["last_used"] = time.time()
            return conn
        
        # Try to get a connection from the pool
        with self._connections_lock:
            if self._connections:
                conn = self._connections.pop()
                self._thread_local.connection = conn
                self._connection_usage[id(conn)]["use_count"] += 1
                self._connection_usage[id(conn)]["last_used"] = time.time()
                return conn
        
        # Create a new connection if the pool is empty
        conn = self._create_connection()
        self._thread_local.connection = conn
        return conn
    
    def _release_connection(self, conn: sqlite3.Connection) -> None:
        """Release a connection back to the pool."""
        if not conn:
            return
        
        # Remove from thread local
        if hasattr(self._thread_local, "connection"):
            if self._thread_local.connection is conn:
                delattr(self._thread_local, "connection")
        
        # Add back to the pool if there's room and connection is still good
        with self._connections_lock:
            if len(self._connections) < self.max_connections:
                try:
                    # Make sure the connection is still usable
                    conn.execute("SELECT 1").fetchone()
                    self._connections.append(conn)
                    return
                except sqlite3.Error:
                    # Connection is no longer usable
                    pass
            
            # If we can't return to the pool, close it
            try:
                conn.close()
            except sqlite3.Error:
                pass
            
            # Remove connection metadata
            conn_id = id(conn)
            if conn_id in self._connection_usage:
                del self._connection_usage[conn_id]
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for getting a database connection.
        
        Yields:
            SQLite connection object
        """
        conn = None
        try:
            conn = self._get_connection()
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {str(e)}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                self._release_connection(conn)
    
    @contextmanager
    def get_cursor(self):
        """
        Context manager for getting a database cursor.
        
        Yields:
            SQLite cursor object
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                conn.commit()
            except:
                conn.rollback()
                raise
            finally:
                cursor.close()
    
    @with_retry(max_attempts=3, retry_on_exceptions=(sqlite3.OperationalError,))
    def execute(self, query: str, params: Optional[Union[tuple, dict]] = None) -> sqlite3.Cursor:
        """
        Execute a SQL query with retry logic.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            SQLite cursor object
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                conn.commit()
                return cursor
            except Exception as e:
                conn.rollback()
                raise
    
    @with_retry(max_attempts=3, retry_on_exceptions=(sqlite3.OperationalError,))
    def executemany(self, query: str, params_seq: List[Union[tuple, dict]]) -> sqlite3.Cursor:
        """
        Execute a SQL query with multiple parameter sets.
        
        Args:
            query: SQL query to execute
            params_seq: Sequence of parameter sets
            
        Returns:
            SQLite cursor object
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, params_seq)
                conn.commit()
                return cursor
            except Exception as e:
                conn.rollback()
                raise
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._connections_lock:
            for conn in self._connections:
                try:
                    conn.close()
                except:
                    pass
            self._connections.clear()
            self._connection_usage.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the connection pool.
        
        Returns:
            Dictionary with connection pool statistics
        """
        with self._connections_lock:
            stats = {
                "pool_size": len(self._connections),
                "max_pool_size": self.max_connections,
                "total_connections": len(self._connection_usage),
                "active_connections": len(self._connection_usage) - len(self._connections),
                "oldest_connection_age": 0,
                "max_usage_count": 0
            }
            
            if self._connection_usage:
                current_time = time.time()
                oldest_time = current_time
                max_count = 0
                
                for meta in self._connection_usage.values():
                    created_at = meta["created_at"]
                    if created_at < oldest_time:
                        oldest_time = created_at
                    
                    use_count = meta["use_count"]
                    if use_count > max_count:
                        max_count = use_count
                
                stats["oldest_connection_age"] = current_time - oldest_time
                stats["max_usage_count"] = max_count
            
            return stats

# Create singleton instance
db_pool = DBConnectionPool(
    db_path=config.get("db_path"),
    timeout=config.get("db_timeout", 20.0)
) 