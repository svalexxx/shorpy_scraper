#!/usr/bin/env python3
"""
Validation utility for Shorpy Scraper.
Checks that the environment is properly configured.
"""

import os
import logging
import sqlite3
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def validate_telegram_config() -> Dict[str, bool]:
    """Validate Telegram configuration."""
    results = {
        "telegram_bot_token": False,
        "telegram_channel_id": False,
        "telegram_report_channel_id": True  # Optional
    }
    
    # Check if required environment variables are set
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        results["telegram_bot_token"] = True
    
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    if channel_id:
        results["telegram_channel_id"] = True
    
    return results

def validate_filesystem() -> Dict[str, bool]:
    """Validate filesystem configuration."""
    results = {
        "output_dir": False,
        "temp_dir": False,
        "writable_output": False,
        "writable_temp": False
    }
    
    # Check if output directory exists and is writable
    output_dir = os.environ.get("OUTPUT_DIR", "scraped_posts")
    if os.path.exists(output_dir):
        results["output_dir"] = True
        # Check if writable
        if os.access(output_dir, os.W_OK):
            results["writable_output"] = True
    
    # Check if temp directory exists and is writable
    temp_dir = os.environ.get("TEMP_DIR", "temp_images")
    if os.path.exists(temp_dir):
        results["temp_dir"] = True
        # Check if writable
        if os.access(temp_dir, os.W_OK):
            results["writable_temp"] = True
    
    return results

def validate_database() -> Dict[str, bool]:
    """Validate database configuration."""
    results = {
        "db_exists": False,
        "db_tables": False,
        "db_writable": False
    }
    
    # Check if database file exists
    db_path = os.environ.get("DB_PATH", "shorpy_data.db")
    if os.path.exists(db_path):
        results["db_exists"] = True
        
        # Check if database has required tables
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check for parsed_posts table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='parsed_posts'")
            if cursor.fetchone():
                # Check for checkpoints table
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'")
                if cursor.fetchone():
                    results["db_tables"] = True
            
            # Check if writable
            try:
                cursor.execute("BEGIN TRANSACTION")
                cursor.execute("ROLLBACK")
                results["db_writable"] = True
            except:
                pass
            
            conn.close()
        except:
            pass
    
    return results

def run_validation() -> Dict[str, Any]:
    """Run all validation checks."""
    logger.info("Running validation checks...")
    
    validation_results = {
        "telegram": validate_telegram_config(),
        "filesystem": validate_filesystem(),
        "database": validate_database(),
        "all_passed": True
    }
    
    # Check if all critical checks passed
    for category, checks in validation_results.items():
        if category == "all_passed":
            continue
            
        for name, passed in checks.items():
            # Skip non-critical checks
            if name == "telegram_report_channel_id":
                continue
                
            if not passed:
                validation_results["all_passed"] = False
                break
    
    return validation_results

def display_validation_results(results: Dict[str, Any]) -> None:
    """Display validation results in a user-friendly format."""
    print("\n=== Shorpy Scraper Validation Results ===\n")
    
    # Telegram validation
    print("Telegram Configuration:")
    telegram_results = results["telegram"]
    print(f"  Bot Token: {'✅' if telegram_results['telegram_bot_token'] else '❌'}")
    print(f"  Channel ID: {'✅' if telegram_results['telegram_channel_id'] else '❌'}")
    print(f"  Report Channel ID: {'✅' if telegram_results['telegram_report_channel_id'] else '⚠️'} (Optional)")
    
    # Filesystem validation
    print("\nFilesystem:")
    fs_results = results["filesystem"]
    print(f"  Output Directory: {'✅' if fs_results['output_dir'] else '❌'}")
    print(f"  Temp Directory: {'✅' if fs_results['temp_dir'] else '❌'}")
    print(f"  Output Directory Writable: {'✅' if fs_results['writable_output'] else '❌'}")
    print(f"  Temp Directory Writable: {'✅' if fs_results['writable_temp'] else '❌'}")
    
    # Database validation
    print("\nDatabase:")
    db_results = results["database"]
    print(f"  Database Exists: {'✅' if db_results['db_exists'] else '❌'}")
    print(f"  Required Tables Exist: {'✅' if db_results['db_tables'] else '❌'}")
    print(f"  Database Writable: {'✅' if db_results['db_writable'] else '❌'}")
    
    # Overall result
    print("\nOverall Result:")
    if results["all_passed"]:
        print("  ✅ All checks passed! The application is properly configured.")
    else:
        print("  ❌ Some checks failed. Please fix the issues above.")
    
    print("\n")

if __name__ == "__main__":
    results = run_validation()
    display_validation_results(results) 