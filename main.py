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
        success = await bot.send_status_report(stats, recipient_username)
        if success:
            logger.info(f"Run report sent successfully to {recipient_username or 'default channel'}")
        else:
            logger.error(f"Failed to send run report to {recipient_username or 'default channel'}")
    except Exception as e:
        logger.error(f"Error sending run report: {str(e)}")

async def process_posts(use_telegram=True, posts_to_process=None, delete_after_processing=False, report_to=None):
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
                        # Mark as published
                        scraper.mark_as_published(post)
                except Exception as e:
                    logger.error(f"Error sending to Telegram: {str(e)}")
                    stats["errors"] += 1
            
            # If we should delete after processing and the post was sent successfully
            if delete_after_processing and telegram_success and post_files:
                try:
                    # Delete the files
                    for file_path in post_files:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"Deleted file after processing: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting files: {str(e)}")
                    stats["errors"] += 1
            
            # If either saved locally or sent to Telegram, mark as processed
            scraper.mark_as_parsed(post)
            logger.info(f"Successfully processed post: {post['title']}")
            
            # Update the last processed post URL in checkpoint
            storage.set_checkpoint('last_post_url', post['post_url'])
            storage.set_checkpoint('last_post_title', post['title'])
            storage.set_checkpoint('last_processed_time', datetime.now().isoformat())
    
    except Exception as e:
        logger.error(f"Error processing posts: {str(e)}")
        stats["errors"] += 1
    
    # Send the run report after every run
    stats["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats["duration"] = str(datetime.now() - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S"))
    if report_to and bot:
        await send_run_report(stats, report_to)
    
    return bot

def save_post_locally(post):
    """Save the post as an HTML file in the output directory."""
    try:
        # Create filename based on post title (sanitized)
        safe_title = ''.join(c if c.isalnum() else '_' for c in post['title'])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_title[:50]}.html"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        # Create HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{post['title']}</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                img {{ max-width: 100%; height: auto; }}
                .post-title {{ font-size: 24px; margin-bottom: 10px; }}
                .post-description {{ margin-bottom: 20px; }}
                .post-image {{ margin-bottom: 20px; }}
                .post-url {{ margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1 class="post-title">{post['title']}</h1>
            
            <div class="post-image">
                {"<img src='" + post['image_url'] + "' alt='" + post['title'] + "'>" if post['image_url'] else "No image available"}
            </div>
            
            <div class="post-description">
                {post['description']}
            </div>
            
            <div class="post-url">
                <a href="{post['post_url']}" target="_blank">Original Post</a>
            </div>
            
            <div class="post-meta">
                Scraped at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            </div>
        </body>
        </html>
        """
        
        # Write HTML to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        # Also save as JSON for potential further processing
        json_filepath = os.path.join(OUTPUT_DIR, f"{timestamp}_{safe_title[:50]}.json")
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(post, f, indent=2)
            
        print(f"Saved post locally: {filepath}")
        return [filepath, json_filepath]  # Return list of created files
        
    except Exception as e:
        print(f"Error saving post locally: {str(e)}")
        return None

def reprocess_existing_posts():
    """Reprocess all posts in the scraped_posts directory."""
    posts = []
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(OUTPUT_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    post = json.load(f)
                    posts.append(post)
            except Exception as e:
                print(f"Error reading post {filename}: {str(e)}")
    return posts

def job():
    # Set use_telegram to True to enable Telegram functionality
    delete_after_processing = os.environ.get('DELETE_AFTER_PROCESSING', 'false').lower() == 'true'
    
    if os.environ.get('REPROCESS_POSTS', 'false').lower() == 'true':
        print("Reprocessing existing posts...")
        posts = reprocess_existing_posts()
        if posts:
            print(f"Found {len(posts)} posts to reprocess")
            asyncio.run(process_posts(use_telegram=True, posts_to_process=posts, delete_after_processing=delete_after_processing))
    else:
        asyncio.run(process_posts(use_telegram=True, delete_after_processing=delete_after_processing))

async def run_setup(use_telegram=True, silent=False, report_to=None):
    """
    Initialize the Telegram bot and test the connection
    
    Args:
        use_telegram: Whether to enable Telegram functionality
        silent: Whether to suppress test messages
        report_to: Optional recipient for reports
        
    Returns:
        The initialized TelegramBot instance or None if Telegram is disabled
    """
    if not use_telegram:
        logger.info("Telegram is disabled, skipping bot initialization")
        return None
        
    try:
        # Just initialize the bot and test the connection
        bot = TelegramBot()
        if not silent:
            await bot.test_connection(silent=True)  # Test but don't send message
        logger.info("Bot initialized successfully")
        return bot
    
    except Exception as e:
        logger.error(f"Error initializing Telegram bot: {str(e)}")
        return None

def print_checkpoint_info():
    """Print information about the last processed post."""
    last_url = storage.get_checkpoint('last_post_url')
    last_title = storage.get_checkpoint('last_post_title')
    last_time = storage.get_checkpoint('last_processed_time')
    
    if last_url and last_title:
        print("\nCheckpoint Information:")
        print(f"Last processed post: {last_title}")
        print(f"URL: {last_url}")
        print(f"Processed at: {last_time or 'Unknown'}")
        print(f"Total posts processed: {storage.get_post_count()}")
    else:
        print("\nNo checkpoint information available yet.")

def purge_scraped_files():
    """Delete all files from the scraped_posts directory."""
    try:
        for filename in os.listdir(OUTPUT_DIR):
            file_path = os.path.join(OUTPUT_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"Deleted: {file_path}")
        print(f"All files in {OUTPUT_DIR} have been deleted.")
    except Exception as e:
        print(f"Error purging scraped files: {str(e)}")

def clean_temp_images():
    """Delete all temporary image files."""
    try:
        if os.path.exists(TEMP_DIR):
            for filename in os.listdir(TEMP_DIR):
                file_path = os.path.join(TEMP_DIR, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"Deleted temp image: {file_path}")
            print(f"Cleaned up all temporary image files.")
    except Exception as e:
        print(f"Error cleaning temp images: {str(e)}")

async def process_test_posts(num_posts=2, delete_files=False, report_to=None):
    """Process a specific number of posts for testing."""
    scraper = ShorpyScraper()
    
    try:
        # Get test posts
        posts = scraper.get_test_posts(num_posts)
        
        if not posts:
            print("No test posts found.")
            return
        
        print(f"Processing {len(posts)} test posts...")
        await process_posts(use_telegram=True, posts_to_process=posts, delete_after_processing=delete_files, report_to=report_to)
        print(f"Completed processing test posts.")
    except Exception as e:
        print(f"Error processing test posts: {str(e)}")

def parse_args():
    """Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(description="Shorpy image scraper")
    
    # Basic mode flags
    parser.add_argument("--run-once", action="store_true", help="Run once and exit")
    parser.add_argument("--check-only", action="store_true", help="Check for new posts but don't send to Telegram")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode with scheduled tasks")
    
    # Debug and testing options
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--silent", action="store_true", help="Suppress Telegram connection test message")
    parser.add_argument("--delete-files", action="store_true", help="Delete post files after processing")
    
    # Action modifiers
    parser.add_argument("--limit", type=int, help="Limit number of posts to process")
    parser.add_argument("--retry", type=int, help="Retry failed posts from previous runs")
    parser.add_argument("--force", action="store_true", help="Force processing of posts (ignore database)")
    
    # Special commands
    parser.add_argument("--validate", action="store_true", help="Run system validation checks")
    parser.add_argument("--repair-db", action="store_true", help="Attempt to repair the SQLite database")
    parser.add_argument("--last-10-posts", action="store_true", help="Send the last 10 posts from the database")
    parser.add_argument("--send-button", action="store_true", help="Send button to channel for last 10 posts")
    parser.add_argument("--monitor", action="store_true", help="Start monitoring API server")
    
    # Configuration
    parser.add_argument("--report-to", type=str, help="Send status report to a specific recipient")
    
    args = parser.parse_args()
    
    # Get default report recipient from environment (if not specified in command line)
    args.report_recipient = args.report_to or os.getenv("TELEGRAM_REPORT_RECIPIENT")
    
    return args

async def main():
    """Main function."""
    
    # Parse command line arguments
    args = parse_args()
    
    # Set up logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    if args.report_recipient:
        logger.info(f"Will send report to: {args.report_recipient}")
    
    # Initialize the bot with proper settings
    if args.validate:
        # Run validation routine
        validation_results = run_validation()
        display_validation_results(validation_results)
        return

    # Initialize Telegram bot if credentials are available
    bot = None
    try:
        bot = await run_setup(use_telegram=not args.check_only, silent=args.silent)
    except Exception as e:
        logger.error(f"Error setting up Telegram: {str(e)}")
        bot = None
        
    # Feature: Send last 10 posts
    if args.last_10_posts and bot:
        await bot.send_last_10_posts()
        logger.info("Last 10 posts sent to Telegram channel")
        return
        
    # Feature: Send button for last 10 posts
    if args.send_button and bot:
        await bot.send_latest_posts_button()
        logger.info("Button for last 10 posts sent to Telegram channel")
        return

    # Regular operation - process posts
    if args.run_once:
        # For run-once mode, directly process posts with proper report recipient
        await process_posts(
            use_telegram=not args.check_only, 
            delete_after_processing=args.delete_files,
            report_to=args.report_recipient  # Use the combined report recipient
        )
        logger.info("Run-once mode enabled, exiting.")
        return
    
    # Schedule mode
    if args.daemon:
        import schedule
        
        # Setup scheduled job
        def scheduled_job():
            asyncio.run(process_posts(
                use_telegram=not args.check_only,
                delete_after_processing=args.delete_files,
                report_to=args.report_recipient
            ))
        
        # Run job immediately
        logger.info("Running initial job...")
        asyncio.run(process_posts(
            use_telegram=not args.check_only,
            delete_after_processing=args.delete_files,
            report_to=args.report_recipient
        ))
        
        # Schedule job to run every 12 hours
        schedule.every(12).hours.do(scheduled_job)
        
        logger.info("Scheduled to run every 12 hours...")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Shutting down...")
    
    # Default behavior - run once but don't exit
    else:
        await process_posts(
            use_telegram=not args.check_only,
            delete_after_processing=args.delete_files,
            report_to=args.report_recipient
        )
        logger.info("Waiting for next run.")
        # Keep script running even in non-schedule mode
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
    
    # Clean up temp files
    clean_temp_images()

def create_index_html():
    """Create an index.html file to browse all saved posts."""
    try:
        posts_files = []
        for filename in os.listdir(OUTPUT_DIR):
            if filename.endswith(".html") and not filename == "index.html":
                # Extract timestamp from filename
                try:
                    timestamp_str = filename.split("_")[0]
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_time = "Unknown"
                
                # Get title from filename
                title = ' '.join(filename.split("_")[1:]).replace(".html", "").replace("_", " ")
                
                posts_files.append({
                    "filename": filename,
                    "title": title,
                    "timestamp": formatted_time
                })
        
        # Sort by timestamp (newest first)
        posts_files.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Create HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Shorpy Scraped Posts</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                h1 {{ margin-bottom: 20px; }}
                .post-list {{ list-style-type: none; padding: 0; }}
                .post-item {{ margin-bottom: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }}
                .post-title {{ font-weight: bold; }}
                .post-timestamp {{ color: #666; font-size: 0.8em; }}
                .post-link {{ text-decoration: none; color: #333; }}
                .post-link:hover {{ background-color: #f5f5f5; }}
            </style>
        </head>
        <body>
            <h1>Shorpy Scraped Posts</h1>
            <p>Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            
            <ul class="post-list">
        """
        
        for post in posts_files:
            html_content += f"""
                <li class="post-item">
                    <a href="{post['filename']}" class="post-link">
                        <div class="post-title">{post['title']}</div>
                        <div class="post-timestamp">{post['timestamp']}</div>
                    </a>
                </li>
            """
        
        html_content += """
            </ul>
        </body>
        </html>
        """
        
        # Write HTML to file
        with open(os.path.join(OUTPUT_DIR, "index.html"), 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print(f"Created index.html with {len(posts_files)} posts")
        
    except Exception as e:
        print(f"Error creating index.html: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 