#!/usr/bin/env python
"""
Simple initialization script to create the database and its tables
for GitHub Actions. This ensures the database is properly set up
before the main script runs.
"""
import sqlite3
import os

DB_PATH = "shorpy_data.db"

def init_db():
    """Initialize the database with the necessary tables."""
    print(f"Initializing database at {DB_PATH}")
    
    # Create the database file if it doesn't exist
    conn = sqlite3.connect(DB_PATH)
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
    
    # Check if there are any records
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM parsed_posts")
    post_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM checkpoints")
    checkpoint_count = cursor.fetchone()[0]
    
    print(f"Database initialized with {table_count} tables")
    print(f"Posts table contains {post_count} records")
    print(f"Checkpoints table contains {checkpoint_count} records")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # Create directories needed by the script
    os.makedirs("scraped_posts", exist_ok=True)
    os.makedirs("temp_images", exist_ok=True)
    
    # Initialize the database
    init_db()
    
    print("Initialization complete") 