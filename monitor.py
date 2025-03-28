#!/usr/bin/env python3
"""
Monitoring script for Shorpy Scraper
Checks system status and sends periodic reports
"""

import os
import sys
import asyncio
import logging
import argparse
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List
from models import storage, get_db_connection
from telegram_bot import TelegramBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("monitor")

async def get_system_stats() -> Dict[str, Any]:
    """
    Collect system statistics and performance data
    """
    stats = {}
    
    # Database stats
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total posts
        cursor.execute("SELECT COUNT(*) FROM parsed_posts")
        stats["total_posts"] = cursor.fetchone()[0]
        
        # Published posts
        cursor.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
        stats["published_posts"] = cursor.fetchone()[0]
        
        # Posts in last 24 hours
        cursor.execute("SELECT COUNT(*) FROM parsed_posts WHERE parsed_at >= datetime('now', '-1 day')")
        stats["posts_last_24h"] = cursor.fetchone()[0]
        
        # Latest post time
        cursor.execute("SELECT MAX(parsed_at) FROM parsed_posts")
        latest_time = cursor.fetchone()[0]
        stats["latest_post_time"] = latest_time
        
        # Check if we've processed any posts recently
        if latest_time:
            latest_dt = datetime.fromisoformat(latest_time.replace(' ', 'T'))
            time_since_last = datetime.now() - latest_dt
            stats["hours_since_last_post"] = round(time_since_last.total_seconds() / 3600, 1)
            
            # Warning flag if no posts in over 48 hours
            stats["stalled"] = time_since_last > timedelta(hours=48)
        
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        stats["db_error"] = str(e)
    
    # System info
    stats["disk_usage"] = get_disk_usage()
    
    # Get last checkpoint info
    stats["last_run"] = storage.get_checkpoint("last_processed_time", "Never")
    stats["last_post_title"] = storage.get_checkpoint("last_post_title", "None")
    
    # Check for potential errors
    log_errors = get_recent_errors()
    stats["error_count"] = len(log_errors)
    if log_errors:
        stats["recent_errors"] = log_errors[:5]  # Only include the 5 most recent errors
    
    return stats

def get_disk_usage() -> Dict[str, Any]:
    """Get disk usage information for the data directories"""
    result = {}
    
    try:
        # Database size
        if os.path.exists("shorpy_data.db"):
            result["db_size_mb"] = round(os.path.getsize("shorpy_data.db") / (1024 * 1024), 2)
        
        # Scraped posts directory size
        if os.path.exists("scraped_posts"):
            total_size = 0
            file_count = 0
            for dirpath, _, filenames in os.walk("scraped_posts"):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
                    file_count += 1
            result["scraped_posts_size_mb"] = round(total_size / (1024 * 1024), 2)
            result["scraped_posts_file_count"] = file_count
        
        # Temp directory check
        if os.path.exists("temp_images"):
            files = os.listdir("temp_images")
            result["temp_files"] = len(files)
            if len(files) > 0:
                result["orphaned_temp_files"] = True
    except Exception as e:
        logger.error(f"Error getting disk usage: {str(e)}")
        result["error"] = str(e)
    
    return result

def get_recent_errors(max_count: int = 10) -> List[str]:
    """Get the most recent errors from the log file"""
    errors = []
    try:
        if os.path.exists("monitor.log"):
            with open("monitor.log", "r") as f:
                for line in f:
                    if "ERROR" in line:
                        errors.append(line.strip())
                        if len(errors) >= max_count:
                            break
    except Exception as e:
        logger.error(f"Error reading log file: {str(e)}")
        return [f"Error reading log file: {str(e)}"]
    
    return errors[::-1]  # Return in reverse order (newest first)

async def send_status_report(detailed: bool = False):
    """Send a status report to Telegram"""
    try:
        stats = await get_system_stats()
        
        # Add stats about when this report was generated
        stats["report_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # For detailed reports, include more information
        if detailed:
            stats["detailed"] = True
        
        # Send the report
        bot = TelegramBot()
        success = await bot.send_status_report(stats)
        
        if success:
            logger.info("Status report sent successfully")
        else:
            logger.error("Failed to send status report")
    
    except Exception as e:
        logger.error(f"Error in send_status_report: {str(e)}")

async def check_health():
    """Check system health and send alerts if there are issues"""
    try:
        stats = await get_system_stats()
        
        # Check for warning conditions
        warnings = []
        
        # No posts in 48 hours
        if stats.get("stalled", False):
            warnings.append(f"No new posts in {stats.get('hours_since_last_post', '?')} hours")
        
        # Database errors
        if "db_error" in stats:
            warnings.append(f"Database error: {stats['db_error']}")
        
        # Recent errors in logs
        if stats.get("error_count", 0) > 0:
            warnings.append(f"Found {stats['error_count']} errors in recent logs")
        
        # Orphaned temp files
        if stats.get("disk_usage", {}).get("orphaned_temp_files", False):
            warnings.append(f"Found {stats['disk_usage']['temp_files']} orphaned temporary files")
        
        # If any warnings, send an alert
        if warnings:
            logger.warning(f"Health check found {len(warnings)} issues")
            
            # Add warnings to the stats
            stats["warnings"] = warnings
            stats["is_alert"] = True
            
            # Send alert report
            bot = TelegramBot()
            await bot.send_status_report(stats)
    
    except Exception as e:
        logger.error(f"Error in check_health: {str(e)}")

async def cleanup_orphaned_files():
    """Clean up any orphaned temporary files"""
    try:
        if os.path.exists("temp_images"):
            files = os.listdir("temp_images")
            if files:
                logger.info(f"Cleaning up {len(files)} orphaned temporary files")
                for file in files:
                    file_path = os.path.join("temp_images", file)
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted: {file_path}")
                    except Exception as e:
                        logger.error(f"Could not delete {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Error in cleanup_orphaned_files: {str(e)}")

async def main():
    parser = argparse.ArgumentParser(description="Shorpy Scraper monitoring tool")
    parser.add_argument("--report", action="store_true", help="Send a status report")
    parser.add_argument("--detailed", action="store_true", help="Include detailed information in the report")
    parser.add_argument("--health-check", action="store_true", help="Run a health check and send alerts if issues found")
    parser.add_argument("--cleanup", action="store_true", help="Clean up orphaned temporary files")
    
    args = parser.parse_args()
    
    if args.report:
        await send_status_report(args.detailed)
    
    if args.health_check:
        await check_health()
    
    if args.cleanup:
        await cleanup_orphaned_files()
        
    # If no arguments provided, show help
    if not (args.report or args.health_check or args.cleanup):
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main()) 