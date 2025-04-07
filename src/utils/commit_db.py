#!/usr/bin/env python
"""
This script is used to automatically commit changes to the database file
when the scraper runs. It will add shorpy_data.db to the staging area
and commit it with a message including the date and time.
"""
import os
import sys
import sqlite3
import subprocess
import logging
import time
from datetime import datetime

# Add the repository root directory to the Python path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(root_dir)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.database.connection import db_pool

def check_for_db_changes():
    """Check if there are any changes to the database file."""
    try:
        # Check if the database file is tracked by git
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "shorpy_data.db"],
            capture_output=True,
            text=True,
            check=False
        )
        
        # If the file is not tracked yet, it should be added
        if result.returncode != 0:
            logger.info("Database file is not tracked yet, will add it")
            return True
        
        # Check if there are changes to the database file
        diff_result = subprocess.run(
            ["git", "diff", "--quiet", "shorpy_data.db"],
            capture_output=True,
            check=False
        )
        
        # Return True if there are changes (non-zero exit code)
        return diff_result.returncode != 0
    except Exception as e:
        logger.error(f"Error checking for database changes: {str(e)}")
        # On error, assume there are changes
        return True

def commit_to_git():
    """Commit the database to Git and push to remote."""
    try:
        # Check if there are changes to commit
        if not check_for_db_changes():
            logger.info("No changes to the database file, skipping commit")
            return True
        
        # Stage the database file
        db_filename = "shorpy_data.db"
        subprocess.run(["git", "add", db_filename], check=True)
        
        # Commit with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_message = f"Update database at {timestamp}"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        
        # Push to remote
        subprocess.run(["git", "push", "origin", "master"], check=True)
        
        # Log success and update checkpoint
        logger.info(f"Successfully committed and pushed database at {timestamp}")
        
        # Update the last commit timestamp in the database
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO checkpoints (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                ("last_db_commit", timestamp)
            )
            conn.commit()
        
        return True
    except Exception as e:
        logger.error(f"Error committing database to Git: {str(e)}")
        return False

def main():
    """Main entry point for the script."""
    logger.info("Starting database commit process")
    success = commit_to_git()
    if success:
        logger.info("Database successfully committed and pushed")
        sys.exit(0)
    else:
        logger.error("Failed to commit database")
        sys.exit(1)

if __name__ == "__main__":
    main() 