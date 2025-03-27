import json
import os
import sqlite3
import threading
from datetime import datetime

# Database initialization
DB_PATH = "shorpy_data.db"

# Thread-local storage for connection
_thread_local = threading.local()

def get_db_connection():
    """Get a thread-safe database connection."""
    if not hasattr(_thread_local, "connection"):
        _thread_local.connection = sqlite3.connect(DB_PATH, timeout=20.0)
    return _thread_local.connection

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create table for parsed posts if it doesn't exist
    cursor.execute('''
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
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Check if published column exists, add it if not
    cursor.execute("PRAGMA table_info(parsed_posts)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'published' not in columns:
        cursor.execute("ALTER TABLE parsed_posts ADD COLUMN published INTEGER DEFAULT 0")
        print("Added 'published' column to parsed_posts table")
    
    conn.commit()

# Call init_db() when this module is imported
init_db()

class Storage:
    def is_post_parsed(self, post_url):
        """Check if a post has already been parsed."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM parsed_posts WHERE post_url = ?", (post_url,))
        result = cursor.fetchone() is not None
        
        return result
    
    def is_post_published(self, post_url):
        """Check if a post has been published to Telegram."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT published FROM parsed_posts WHERE post_url = ?", (post_url,))
        result = cursor.fetchone()
        
        if result:
            return bool(result[0])
        return False
    
    def mark_post_published(self, post_url):
        """Mark a post as published to Telegram."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE parsed_posts SET published = 1 WHERE post_url = ?",
                (post_url,)
            )
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Database error marking post as published: {e}")
            conn.rollback()
            return False
    
    def add_post(self, post_data):
        """Add a post to the database."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO parsed_posts (post_url, title, image_url, description, published) VALUES (?, ?, ?, ?, ?)",
                (post_data['post_url'], post_data['title'], post_data.get('image_url', ''), 
                 post_data.get('description', ''), post_data.get('is_published', 0))
            )
            
            # Update the last_post checkpoint with this post URL
            self.set_checkpoint('last_post_url', post_data['post_url'])
            self.set_checkpoint('last_post_title', post_data['title'])
            self.set_checkpoint('last_processed_time', datetime.now().isoformat())
            
            conn.commit()
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            conn.rollback()
    
    def get_checkpoint(self, key, default=None):
        """Get the value of a checkpoint."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM checkpoints WHERE key = ?", (key,))
        result = cursor.fetchone()
        
        if result:
            return result[0]
        return default
    
    def set_checkpoint(self, key, value):
        """Set the value of a checkpoint."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Update the checkpoint, or insert if it doesn't exist
            cursor.execute(
                "INSERT OR REPLACE INTO checkpoints (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, value)
            )
            
            conn.commit()
        except sqlite3.Error as e:
            print(f"Database error setting checkpoint {key}: {e}")
            conn.rollback()
    
    def get_post_count(self):
        """Get the number of parsed posts."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM parsed_posts")
        count = cursor.fetchone()[0]
        
        return count
    
    def get_latest_posts(self, limit=10):
        """Get the most recent parsed posts."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT post_url, title, image_url, description, parsed_at, published FROM parsed_posts ORDER BY parsed_at DESC LIMIT ?",
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
                'is_published': bool(row[5])
            })
        
        return posts

# Create a singleton instance
storage = Storage() 