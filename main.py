import asyncio
import schedule
import time
import os
import json
import sys
import argparse
import shutil
import logging
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

from src.scraper.shorpy import ShorpyScraper
from src.bot.telegram_bot import TelegramBot
from src.database.models import storage
from src.database.connection import db_pool
from src.utils.monitor import get_system_stats
from src.utils.validate import run_validation, display_validation_results

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shorpy_scraper')

# Create output directory
OUTPUT_DIR = "scraped_posts"
TEMP_DIR = "temp_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

async def test_telegram_connection(silent=True):
    """Test if the bot can connect to Telegram and send a message."""
    try:
        bot = TelegramBot()
        return await bot.test_connection(silent)
    except Exception as e:
        print(f"Error testing Telegram connection: {str(e)}")
        return False

async def send_run_report(stats, recipient_username=None):
    """Send a run report to a specific recipient or the default channel.
    
    Args:
        stats: Dictionary containing run statistics
        recipient_username: Optional username or chat ID to send report to
    """
    try:
        bot = TelegramBot()
        logger.info(f"Sending run report to {recipient_username or 'default channel'}")
        
        # Make sure disk usage info is populated
        if "disk_usage" not in stats:
            stats["disk_usage"] = {}
            
            # Try to get database size
            for db_name in ["shorpy.db", "shorpy_data.db"]:
                for search_dir in [".", "src", ".."]:
                    db_path = os.path.join(os.getcwd(), search_dir, db_name)
                    if os.path.exists(db_path):
                        db_size = os.path.getsize(db_path) / (1024 * 1024)  # Convert to MB
                        stats["disk_usage"]["db_size_mb"] = round(db_size, 2)
                        break
            
            # Get scraped posts size
            for posts_dir_name in ["scraped_posts", "posts", "images"]:
                posts_dir = os.path.join(os.getcwd(), posts_dir_name)
                if os.path.exists(posts_dir) and os.path.isdir(posts_dir):
                    size = 0
                    file_count = 0
                    for path, dirs, files in os.walk(posts_dir):
                        for f in files:
                            fp = os.path.join(path, f)
                            size += os.path.getsize(fp)
                            file_count += 1
                    
                    size_mb = size / (1024 * 1024)  # Convert to MB
                    stats["disk_usage"]["scraped_posts_size_mb"] = round(size_mb, 2) if "scraped_posts_size_mb" not in stats["disk_usage"] else stats["disk_usage"]["scraped_posts_size_mb"]
                    stats["disk_usage"]["scraped_posts_file_count"] = file_count if "scraped_posts_file_count" not in stats["disk_usage"] else stats["disk_usage"]["scraped_posts_file_count"]
                    break
        
        # Make sure database stats are populated
        try:
            # Import database connection
            from src.database.connection import db_pool
            
            if "total_posts" not in stats:
                try:
                    # Try with parsed_posts first (older version)
                    try:
                        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts")
                        stats["total_posts"] = cursor.fetchone()[0]
                        
                        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
                        stats["published_posts"] = cursor.fetchone()[0]
                        
                        # Get posts from last 24 hours
                        cursor = db_pool.execute(
                            "SELECT COUNT(*) FROM parsed_posts WHERE parsed_at >= datetime('now', '-1 day')"
                        )
                        stats["posts_last_24h"] = cursor.fetchone()[0]
                    except Exception:
                        # Try with new schema if old one fails
                        logger.info("Trying with 'posts' table instead of 'parsed_posts'")
                        cursor = db_pool.execute("SELECT COUNT(*) FROM posts")
                        stats["total_posts"] = cursor.fetchone()[0]
                        
                        cursor = db_pool.execute("SELECT COUNT(*) FROM posts WHERE published = 1")
                        stats["published_posts"] = cursor.fetchone()[0]
                        
                        # Get posts from last 24 hours
                        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                        cursor = db_pool.execute("SELECT COUNT(*) FROM posts WHERE timestamp > ?", (yesterday,))
                        stats["posts_last_24h"] = cursor.fetchone()[0]
                except Exception as e:
                    logger.error(f"Error getting database stats: {str(e)}")
                    stats["total_posts"] = 0
                    stats["published_posts"] = 0
                    stats["posts_last_24h"] = 0
        except ImportError as e:
            logger.error(f"Error importing db_pool: {str(e)}")
            stats["total_posts"] = 0
            stats["published_posts"] = 0
            stats["posts_last_24h"] = 0
        
        # Send the report
        await bot.send_status_report(stats, recipient_username)
        logger.info(f"Run report sent successfully to {recipient_username or 'default channel'}")
    except Exception as e:
        logger.error(f"Error sending run report: {str(e)}")

class ProcessingFailed(Exception):
    """Raised (only when raise_on_error=True) if a run finished with errors."""


async def process_posts(use_telegram=True, posts_to_process=None, delete_after_processing=False, report_to=None,
                        raise_on_error=False):
    scraper = ShorpyScraper()
    stats = {
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "posts_processed": 0,
        "posts_sent": 0,
        "errors": 0,
        "warnings": [],
        "disk_usage": {
            "db_size_mb": 0.0,
            "scraped_posts_size_mb": 0.0,
            "scraped_posts_file_count": 0
        }
    }
    
    # Initialize Telegram bot if needed
    bot = None
    if use_telegram:
        try:
            bot = TelegramBot()
            logger.info("Telegram bot initialized successfully.")
        except Exception as e:
            logger.error(f"Could not initialize Telegram bot: {str(e)}")
            if raise_on_error:
                # Don't silently mark posts as parsed without sending them
                raise
            use_telegram = False
            stats["errors"] += 1
    
    try:
        # Get posts to process
        posts = posts_to_process if posts_to_process is not None else scraper.get_latest_posts()
        
        if not posts:
            logger.info("No posts to process.")
            # If Telegram is enabled and this is not a test run (real scheduled run)
            if use_telegram and posts_to_process is None and bot:
                try:
                    # Send only detailed report to the specified recipient, no notification to main channel
                    if report_to:
                        await bot.send_no_posts_message(send_detailed_report=True, send_notification=False, recipient=report_to)
                    else:
                        # This is the old behavior: notification to channel with no detailed report
                        await bot.send_no_posts_message(send_detailed_report=False, send_notification=True)
                except Exception as e:
                    logger.error(f"Error sending 'no posts' message: {str(e)}")
                    stats["errors"] += 1
            
            # Add warning for no posts found
            stats["warnings"].append("No new posts found during this check")
            
            # Always prepare stats for reports when no posts are found
            stats["total_posts_found"] = 0
            stats["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            stats["duration"] = str(datetime.now() - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S"))
            
            # Always send a report if a recipient is specified
            if report_to and bot:
                logger.info(f"Sending detailed report to {report_to}")
                await send_run_report(stats, report_to)
            
            return bot
            
        logger.info(f"Found {len(posts)} posts to process.")
        stats["total_posts_found"] = len(posts)
        
        # Filter out posts that have already been published (unless in test mode)
        if posts_to_process is None:  # Not in test mode
            new_posts = [post for post in posts if not post.get('is_published', False)]
            if len(new_posts) != len(posts):
                logger.info(f"Filtered out {len(posts) - len(new_posts)} already published posts.")
                stats["filtered_posts"] = len(posts) - len(new_posts)
                posts = new_posts
                
            if not posts:
                logger.info("No new posts to send to Telegram.")
                
                # Add warning for all posts being filtered out
                stats["warnings"].append("All found posts were already published")
                
                # Always prepare stats for reports when no new posts are found
                stats["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                stats["duration"] = str(datetime.now() - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S"))
                
                # Always send a report if a recipient is specified
                if report_to and bot:
                    logger.info(f"Sending detailed report to {report_to}")
                    await send_run_report(stats, report_to)
                
                return bot
                
        # Process each post
        for post in posts:
            # Save post locally
            post_files = save_post_locally(post)
            stats["posts_processed"] += 1
            
            # Try sending to Telegram if enabled
            telegram_success = False
            if use_telegram and bot:
                try:
                    logger.info(f"Attempting to send post to Telegram: {post['title']}")
                    telegram_success = await bot.send_post(post)
                    if telegram_success:
                        logger.info(f"Successfully sent post to Telegram: {post['title']}")
                        stats["posts_sent"] += 1
                        # Mark as parsed and published only after successful sending
                        scraper.mark_as_parsed(post)
                        scraper.mark_as_published(post)
                except Exception as e:
                    logger.error(f"Error sending to Telegram: {str(e)}")
                    stats["errors"] += 1
            else:
                # If Telegram is not enabled, just mark as parsed
                scraper.mark_as_parsed(post)
            
            # If we should delete after processing and the post was sent successfully
            if delete_after_processing and telegram_success:
                for file_path in post_files:
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted file: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting file {file_path}: {str(e)}")
                        stats["errors"] += 1
        
        # Update stats
        stats["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats["duration"] = str(datetime.now() - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S"))
        
        # Send report if recipient specified
        if report_to and bot:
            logger.info(f"Sending detailed report to {report_to}")
            await send_run_report(stats, report_to)
        
        if raise_on_error and stats["errors"]:
            raise ProcessingFailed(f"Run finished with {stats['errors']} error(s)")
        
        return bot
    except ProcessingFailed:
        raise
    except Exception as e:
        logger.error(f"Error in process_posts: {str(e)}")
        stats["errors"] += 1
        stats["warnings"].append(f"Error during processing: {str(e)}")
        
        # Try to send error report
        if report_to and bot:
            logger.info(f"Sending error report to {report_to}")
            await send_run_report(stats, report_to)
        
        if raise_on_error:
            raise
        return bot

def save_post_locally(post):
    """Save a post's content and images locally.
    
    Args:
        post: Dictionary containing post data
        
    Returns:
        list: List of saved file paths
    """
    saved_files = []
    
    try:
        # Create post directory
        post_dir = os.path.join(OUTPUT_DIR, post['post_id'])
        os.makedirs(post_dir, exist_ok=True)
        
        # Save post metadata
        metadata_path = os.path.join(post_dir, 'metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(post, f, indent=4)
        saved_files.append(metadata_path)
        
        # Save post content
        content_path = os.path.join(post_dir, 'content.txt')
        with open(content_path, 'w') as f:
            f.write(f"Title: {post['title']}\n\n")
            f.write(f"Description: {post['description']}\n\n")
            f.write(f"URL: {post['post_url']}\n")
            if post.get('image_url'):
                f.write(f"Image URL: {post['image_url']}\n")
        saved_files.append(content_path)
        
        return saved_files
    except Exception as e:
        logger.error(f"Error saving post locally: {str(e)}")
        return []

async def reprocess_existing_posts():
    """Reprocess all posts in the database that haven't been published."""
    try:
        cursor = db_pool.execute("SELECT * FROM parsed_posts WHERE published = 0")
        posts = cursor.fetchall()
        
        if posts:
            logger.info(f"Found {len(posts)} unpublished posts to reprocess")
            await process_posts(posts_to_process=posts)
        else:
            logger.info("No unpublished posts found to reprocess")
    except Exception as e:
        logger.error(f"Error reprocessing posts: {str(e)}")

def job():
    """Run the scraper job."""
    logger.info("Starting scheduled job")
    asyncio.run(process_posts(use_telegram=True))
    logger.info("Finished scheduled job")

async def run_setup(use_telegram=True, silent=False, report_to=None):
    """Run initial setup and validation.
    
    Args:
        use_telegram: Whether to test Telegram functionality
        silent: Whether to suppress test messages
        report_to: Optional username or chat ID to send reports to
    """
    try:
        # Run validation checks
        validation_results = run_validation()
        display_validation_results(validation_results)
        
        if use_telegram:
            # Test Telegram connection
            logger.info("Testing Telegram connection...")
            telegram_success = await test_telegram_connection(silent)
            
            if telegram_success:
                logger.info("✅ Telegram connection test successful")
                
                if report_to:
                    # Send a test report
                    stats = {
                        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "duration": "0:00:01",
                        "total_posts_found": 0,
                        "posts_processed": 0,
                        "posts_sent": 0,
                        "warnings": ["This is a test report"],
                        "disk_usage": {}
                    }
                    await send_run_report(stats, report_to)
            else:
                logger.error("❌ Telegram connection test failed")
                return False
        
        return True
    except Exception as e:
        logger.error(f"Error during setup: {str(e)}")
        return False

def print_checkpoint_info():
    """Print information about the last processed post."""
    try:
        last_url = storage.get_checkpoint('last_post_url')
        last_title = storage.get_checkpoint('last_post_title')
        last_time = storage.get_checkpoint('last_processed_time')
        
        if last_url and last_title and last_time:
            print("\nLast processed post:")
            print(f"Title: {last_title}")
            print(f"URL: {last_url}")
            print(f"Time: {last_time}")
        else:
            print("\nNo checkpoint information found")
    except Exception as e:
        logger.error(f"Error getting checkpoint info: {str(e)}")

def purge_scraped_files():
    """Delete all scraped files."""
    try:
        if os.path.exists(OUTPUT_DIR):
            shutil.rmtree(OUTPUT_DIR)
            os.makedirs(OUTPUT_DIR)
            logger.info(f"Purged all files in {OUTPUT_DIR}")
        else:
            logger.info(f"Directory {OUTPUT_DIR} does not exist")
    except Exception as e:
        logger.error(f"Error purging scraped files: {str(e)}")

def clean_temp_images():
    """Delete all temporary image files."""
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            os.makedirs(TEMP_DIR)
            logger.info(f"Cleaned all files in {TEMP_DIR}")
        else:
            logger.info(f"Directory {TEMP_DIR} does not exist")
    except Exception as e:
        logger.error(f"Error cleaning temp images: {str(e)}")

async def process_test_posts(num_posts=2, delete_files=False, report_to=None, force=False):
    """Process a few test posts without marking them as parsed/published.
    
    Args:
        num_posts: Number of posts to process for testing
        delete_files: Whether to delete downloaded files after processing
        report_to: Optional username or chat ID to send reports to
        force: Whether to process posts even if already parsed
    """
    scraper = ShorpyScraper()
    posts = scraper.get_test_posts(num_posts)
    if force:
        # Reset the is_published flag for testing
        for post in posts:
            post['is_published'] = False
    await process_posts(posts_to_process=posts, delete_after_processing=delete_files, report_to=report_to)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Shorpy Image Scraper')
    
    # Add arguments
    parser.add_argument('--setup', action='store_true',
                       help='Run setup and validation')
    parser.add_argument('--no-telegram', action='store_true',
                       help='Disable Telegram functionality')
    parser.add_argument('--silent', action='store_true',
                       help='Suppress test messages')
    parser.add_argument('--schedule', action='store_true',
                       help='Run as a scheduled job')
    parser.add_argument('--interval', type=int, default=60,
                       help='Interval between runs in minutes (default: 60)')
    parser.add_argument('--test', action='store_true',
                       help='Run in test mode')
    parser.add_argument('--test-posts', type=int, default=2,
                       help='Number of posts to process in test mode (default: 2)')
    parser.add_argument('--delete-files', action='store_true',
                       help='Delete downloaded files after processing')
    parser.add_argument('--clean', action='store_true',
                       help='Clean temporary files')
    parser.add_argument('--purge', action='store_true',
                       help='Purge all scraped files')
    parser.add_argument('--checkpoint', action='store_true',
                       help='Show checkpoint information')
    parser.add_argument('--reprocess', action='store_true',
                       help='Reprocess unpublished posts')
    parser.add_argument('--report-to',
                       help='Username or chat ID to send reports to')
    parser.add_argument('--force', action='store_true',
                       help='Force processing of posts even if already parsed')
    
    return parser.parse_args()

async def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Parse arguments
    args = parse_args()
    
    # Handle cleaning/purging first
    if args.clean:
        clean_temp_images()
        return
    
    if args.purge:
        purge_scraped_files()
        return
    
    if args.checkpoint:
        print_checkpoint_info()
        return
    
    # Run setup if requested
    if args.setup:
        success = await run_setup(
            use_telegram=not args.no_telegram,
            silent=args.silent,
            report_to=args.report_to
        )
        if not success:
            logger.error("Setup failed")
            sys.exit(1)
        return
    
    # Reprocess unpublished posts if requested
    if args.reprocess:
        await reprocess_existing_posts()
        return
    
    # Run in test mode if requested
    if args.test:
        await process_test_posts(
            num_posts=args.test_posts,
            delete_files=args.delete_files,
            report_to=args.report_to,
            force=args.force
        )
        return
    
    # Run as a scheduled job if requested
    if args.schedule:
        logger.info(f"Starting scheduled job with {args.interval} minute interval")
        
        # Schedule the job
        schedule.every(args.interval).minutes.do(job)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Scheduled job stopped by user")
        except Exception as e:
            logger.error(f"Error in scheduled job: {str(e)}")
        return
    
    # Run once if no other mode specified
    await process_posts(
        use_telegram=not args.no_telegram,
        delete_after_processing=args.delete_files,
        report_to=args.report_to,
        raise_on_error=True
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program stopped by user")
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        sys.exit(1) 