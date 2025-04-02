import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union

from src.database.connection import db_pool
from src.utils.error_handler import with_retry, safe_execute
from src.utils.metrics import metrics, counted, timed

# Set up logger
logger = logging.getLogger(__name__)

# Initialize database schema
def init_db():
    """Initialize the database schema if it doesn't exist."""
    try:
        # Create table for parsed posts if it doesn't exist
        db_pool.execute('''
        CREATE TABLE IF NOT EXISTS parsed_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_url TEXT UNIQUE,
            title TEXT,
            image_url TEXT,
            description TEXT,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published INTEGER DEFAULT 0
        )
        ''')
        
        # Create table for checkpoints if it doesn't exist
        db_pool.execute('''
        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Check if published column exists, add it if not
        cursor = db_pool.execute("PRAGMA table_info(parsed_posts)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'published' not in columns:
            db_pool.execute("ALTER TABLE parsed_posts ADD COLUMN published INTEGER DEFAULT 0")
            logger.info("Added 'published' column to parsed_posts table")
            
        # Create metrics table if it doesn't exist
        db_pool.execute('''
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            value REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
        ''')
        
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

# Call init_db() when this module is imported
init_db()

class Storage:
    """Storage operations for parsed posts and application state."""
    
    @counted("storage.is_post_parsed")
    @timed("storage.is_post_parsed")
    @with_retry(max_attempts=3)
    def is_post_parsed(self, post_url: str) -> bool:
        """
        Check if a post has already been parsed.
        
        Args:
            post_url: URL of the post to check
            
        Returns:
            True if the post has been parsed, False otherwise
        """
        cursor = db_pool.execute("SELECT 1 FROM parsed_posts WHERE post_url = ?", (post_url,))
        result = cursor.fetchone() is not None
        
        metrics.increment_counter("posts.checked")
        return result
    
    @counted("storage.is_post_published")
    @timed("storage.is_post_published")
    @with_retry(max_attempts=3)
    def is_post_published(self, post_url: str) -> bool:
        """
        Check if a post has been published to Telegram.
        
        Args:
            post_url: URL of the post to check
            
        Returns:
            True if the post has been published, False otherwise
        """
        cursor = db_pool.execute("SELECT published FROM parsed_posts WHERE post_url = ?", (post_url,))
        result = cursor.fetchone()
        
        if result:
            return bool(result[0])
        return False
    
    @counted("storage.mark_post_published")
    @timed("storage.mark_post_published")
    @with_retry(max_attempts=3)
    def mark_post_published(self, post_url: str) -> bool:
        """
        Mark a post as published to Telegram.
        
        Args:
            post_url: URL of the post to mark as published
            
        Returns:
            True if successful, False otherwise
        """
        try:
            db_pool.execute(
                "UPDATE parsed_posts SET published = 1 WHERE post_url = ?",
                (post_url,)
            )
            
            metrics.increment_counter("posts.published")
            return True
        except Exception as e:
            logger.error(f"Database error marking post as published: {str(e)}")
            return False
    
    @counted("storage.add_post")
    @timed("storage.add_post")
    @with_retry(max_attempts=3)
    def add_post(self, post_data: Dict[str, Any]) -> bool:
        """
        Add a post to the database.
        
        Args:
            post_data: Dictionary with post data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            db_pool.execute(
                "INSERT OR REPLACE INTO parsed_posts (post_url, title, image_url, description, published) VALUES (?, ?, ?, ?, ?)",
                (post_data['post_url'], post_data['title'], post_data.get('image_url', ''), 
                 post_data.get('description', ''), post_data.get('is_published', 0))
            )
            
            # Update the last_post checkpoint with this post URL
            self.set_checkpoint('last_post_url', post_data['post_url'])
            self.set_checkpoint('last_post_title', post_data['title'])
            self.set_checkpoint('last_processed_time', datetime.now().isoformat())
            
            metrics.increment_counter("posts.added")
            return True
        except Exception as e:
            logger.error(f"Database error adding post: {str(e)}")
            return False
    
    @counted("storage.get_checkpoint")
    @with_retry(max_attempts=3)
    def get_checkpoint(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get the value of a checkpoint.
        
        Args:
            key: Key of the checkpoint
            default: Default value if checkpoint doesn't exist
            
        Returns:
            Checkpoint value or default
        """
        cursor = db_pool.execute("SELECT value FROM checkpoints WHERE key = ?", (key,))
        result = cursor.fetchone()
        
        if result:
            return result[0]
        return default
    
    @counted("storage.set_checkpoint")
    @with_retry(max_attempts=3)
    def set_checkpoint(self, key: str, value: str) -> bool:
        """
        Set the value of a checkpoint.
        
        Args:
            key: Key of the checkpoint
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update the checkpoint, or insert if it doesn't exist
            db_pool.execute(
                "INSERT OR REPLACE INTO checkpoints (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, value)
            )
            
            return True
        except Exception as e:
            logger.error(f"Database error setting checkpoint {key}: {str(e)}")
            return False
    
    @counted("storage.get_post_count")
    @with_retry(max_attempts=3)
    def get_post_count(self) -> int:
        """
        Get the number of parsed posts.
        
        Returns:
            Number of parsed posts
        """
        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts")
        count = cursor.fetchone()[0]
        
        return count
    
    @counted("storage.get_latest_posts")
    @timed("storage.get_latest_posts")
    @with_retry(max_attempts=3)
    def get_latest_posts(self, limit: int = 10, published_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get the most recent parsed posts.
        
        Args:
            limit: Maximum number of posts to return
            published_only: Whether to return only published posts
            
        Returns:
            List of post dictionaries
        """
        query = """
            SELECT post_url, title, image_url, description, parsed_at, published 
            FROM parsed_posts 
            {}
            ORDER BY parsed_at DESC LIMIT ?
        """
        
        query = query.format("WHERE published = 1" if published_only else "")
        
        cursor = db_pool.execute(query, (limit,))
        
        posts = []
        for row in cursor.fetchall():
            posts.append({
                'post_url': row[0],
                'title': row[1],
                'image_url': row[2],
                'description': row[3],
                'parsed_at': row[4],
                'is_published': bool(row[5])
            })
        
        return posts
    
    @counted("storage.get_unpublished_posts")
    @with_retry(max_attempts=3)
    def get_unpublished_posts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get posts that haven't been published yet.
        
        Args:
            limit: Maximum number of posts to return
            
        Returns:
            List of unpublished post dictionaries
        """
        cursor = db_pool.execute(
            """
            SELECT post_url, title, image_url, description, parsed_at 
            FROM parsed_posts 
            WHERE published = 0
            ORDER BY parsed_at ASC LIMIT ?
            """,
            (limit,)
        )
        
        posts = []
        for row in cursor.fetchall():
            posts.append({
                'post_url': row[0],
                'title': row[1],
                'image_url': row[2],
                'description': row[3],
                'parsed_at': row[4],
                'is_published': False
            })
        
        return posts
    
    @counted("storage.record_metric")
    def record_metric(self, name: str, value: float, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Record a metric in the database.
        
        Args:
            name: Name of the metric
            value: Value of the metric
            metadata: Additional metadata for the metric
            
        Returns:
            True if successful, False otherwise
        """
        try:
            metadata_json = json.dumps(metadata) if metadata else None
            
            db_pool.execute(
                "INSERT INTO metrics (name, value, timestamp, metadata) VALUES (?, ?, datetime('now'), ?)",
                (name, value, metadata_json)
            )
            
            return True
        except Exception as e:
            logger.error(f"Error recording metric {name}: {str(e)}")
            return False
    
    @counted("storage.get_metrics")
    def get_metrics(self, name: str, from_time: Optional[datetime] = None, 
                   to_time: Optional[datetime] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get metrics from the database.
        
        Args:
            name: Name of the metric
            from_time: Start time for metrics
            to_time: End time for metrics
            limit: Maximum number of metrics to return
            
        Returns:
            List of metric dictionaries
        """
        query = "SELECT id, name, value, timestamp, metadata FROM metrics WHERE name = ?"
        params = [name]
        
        if from_time:
            query += " AND timestamp >= ?"
            params.append(from_time.isoformat())
        
        if to_time:
            query += " AND timestamp <= ?"
            params.append(to_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        try:
            cursor = db_pool.execute(query, tuple(params))
            
            metrics_list = []
            for row in cursor.fetchall():
                metadata = json.loads(row[4]) if row[4] else {}
                metrics_list.append({
                    'id': row[0],
                    'name': row[1],
                    'value': row[2],
                    'timestamp': row[3],
                    'metadata': metadata
                })
            
            return metrics_list
        except Exception as e:
            logger.error(f"Error getting metrics {name}: {str(e)}")
            return []

# Create a singleton instance
storage = Storage() 