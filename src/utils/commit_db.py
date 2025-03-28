#!/usr/bin/env python
"""
Helper script to commit database changes to GitHub.
This simplifies the GitHub Actions workflow by handling the Git operations in Python.
"""
import os
import sys
import subprocess
import logging
from datetime import datetime

from src.database.models import get_db_connection

def run_command(command):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}")
        print(f"Error message: {e.stderr}")
        return None

def setup_git():
    """Configure Git with GitHub Actions bot info."""
    print("Setting up Git configuration...")
    run_command('git config --global user.name "github-actions[bot]"')
    run_command('git config --global user.email "github-actions[bot]@users.noreply.github.com"')
    print("Git configuration completed")

def backup_database():
    """Create a backup of the database file."""
    print("Creating database backup...")
    if os.path.exists("shorpy_data.db"):
        run_command("cp shorpy_data.db shorpy_data.db.bak")
        print("Database backup created")
    else:
        print("Database file not found, cannot create backup")

def update_repository():
    """Pull the latest changes from the repository."""
    print("Pulling latest changes from repository...")
    output = run_command("git pull")
    print(f"Git pull result: {output}")

def restore_database():
    """Restore the database from backup if needed."""
    print("Checking if database restoration is needed...")
    if not os.path.exists("shorpy_data.db") and os.path.exists("shorpy_data.db.bak"):
        print("Database file missing, restoring from backup...")
        run_command("cp shorpy_data.db.bak shorpy_data.db")
        print("Database restored from backup")
    else:
        print("No restoration needed")

def commit_changes():
    """Commit and push database changes if any."""
    print("Checking for changes to commit...")
    
    # Get status
    status = run_command("git status --porcelain")
    print(f"Git status: {status}")
    
    # Add database file
    run_command("git add -f shorpy_data.db")
    print("Added database file to staging area")
    
    # Check if there are changes to commit
    diff_output = run_command("git diff --cached --name-only")
    if "shorpy_data.db" in diff_output:
        print("Changes detected, committing...")
        commit_result = run_command('git commit -m "Update checkpoint data [skip ci]"')
        print(f"Commit result: {commit_result}")
        
        push_result = run_command("git push")
        print(f"Push result: {push_result}")
        return True
    else:
        print("No changes to commit")
        return False

def main():
    """Main execution function."""
    print("Starting database commit process...")
    
    # Setup Git
    setup_git()
    
    # Backup database
    backup_database()
    
    # Update repository
    update_repository()
    
    # Restore database if needed
    restore_database()
    
    # Commit changes
    changes_committed = commit_changes()
    
    # Clean up backup
    if os.path.exists("shorpy_data.db.bak"):
        os.remove("shorpy_data.db.bak")
        print("Removed database backup")
    
    print("Database commit process completed")
    return 0 if changes_committed else 0  # Always return success

if __name__ == "__main__":
    sys.exit(main()) 