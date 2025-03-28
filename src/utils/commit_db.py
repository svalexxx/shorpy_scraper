#!/usr/bin/env python
"""
This script is used to automatically commit changes to the database file
when the scraper runs. It will add shorpy_data.db to the staging area
and commit it with a message including the date and time.
"""
import os
import sys
import subprocess
import logging
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from src.database.models import get_db_connection
except ImportError:
    # Fallback to direct import if src package is not found
    import sqlite3
    def get_db_connection():
        return sqlite3.connect('shorpy_data.db')

def run_command(command):
    """Run a shell command and return the output."""
    process = subprocess.Popen(
        command, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        shell=True
    )
    stdout, stderr = process.communicate()
    return stdout.decode(), stderr.decode(), process.returncode

def main():
    print("Starting DB commit process...")
    
    # Get the current date and time for the commit message
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if the database file exists
    if not os.path.exists('shorpy_data.db'):
        print("Database file not found. Nothing to commit.")
        return
    
    # Get database stats for the commit message
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total posts
        cursor.execute("SELECT COUNT(*) FROM parsed_posts")
        total_posts = cursor.fetchone()[0]
        
        # Get published posts
        cursor.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
        published_posts = cursor.fetchone()[0]
        
        # Get recent changes
        cursor.execute("""
            SELECT COUNT(*) FROM parsed_posts 
            WHERE datetime(published_at) > datetime('now', '-1 day')
        """)
        recent_changes = cursor.fetchone()[0]
        
        conn.close()
        
        commit_message = f"Update database: {now} | {total_posts} total posts, {published_posts} published, {recent_changes} recent changes"
    except Exception as e:
        print(f"Error getting database stats: {str(e)}")
        commit_message = f"Update database: {now}"
    
    # Stage the database file
    stdout, stderr, code = run_command("git add shorpy_data.db")
    if code != 0:
        print(f"Error staging database file: {stderr}")
        return
    
    # Check if there are changes to commit
    stdout, stderr, code = run_command("git diff --cached --quiet")
    if code == 0:
        print("No changes to commit.")
        return
    
    # Commit the changes
    stdout, stderr, code = run_command(f'git commit -m "{commit_message}"')
    if code != 0:
        print(f"Error committing changes: {stderr}")
        return
    
    print(f"Committed database changes: {commit_message}")
    
    # Push the changes to remote
    stdout, stderr, code = run_command("git push")
    if code != 0:
        print(f"Error pushing changes: {stderr}")
        return
    
    print("Successfully pushed database changes to remote.")

if __name__ == "__main__":
    main() 