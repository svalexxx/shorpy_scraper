#!/usr/bin/env python
"""
Create an empty database file to be committed to the repository.
This allows GitHub Actions to modify and commit the file later.
"""
import sqlite3
import os

DB_PATH = "shorpy_data.db"

def create_empty_db():
    """Create an empty database with the basic schema."""
    print(f"Creating empty database at {DB_PATH}")
    
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
    
    # Insert a dummy checkpoint to indicate this is a properly initialized database
    cursor.execute(
        "INSERT OR REPLACE INTO checkpoints (key, value) VALUES (?, ?)",
        ("init_timestamp", os.environ.get("GITHUB_SHA", "local") + "_" + os.environ.get("GITHUB_RUN_ID", str(os.getpid())))
    )
    
    conn.commit()
    conn.close()
    
    print(f"Empty database created at {DB_PATH}")

if __name__ == "__main__":
    create_empty_db()
    print("You can now commit this empty database file to your repository.") 