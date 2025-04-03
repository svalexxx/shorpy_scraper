import asyncio
import schedule
import time
import os
import json
import sys
import argparse
import shutil
import logging
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from src.scraper.shorpy import ShorpyScraper
from src.bot.telegram_bot import TelegramBot
from src.database.models import storage
from src.database.connection import db_pool
from src.utils.monitor import get_system_stats

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

async def test_telegram_connection(silent=False):
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
        recipient_username: Optional username to send report to (e.g., @username)
    """
    try:
        bot = TelegramBot()
        if recipient_username:
            await bot.send_status_report(stats, recipient_username)
        else:
            await bot.send_status_report(stats)
        logger.info(f"Run report sent to {recipient_username or 'default channel'}")
    except Exception as e:
        logger.error(f"Error sending run report: {str(e)}")

async def process_posts(use_telegram=True, posts_to_process=None, delete_after_processing=False, report_to=None):
    scraper = ShorpyScraper()
    stats = {
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "posts_processed": 0,
        "posts_sent": 0,
        "errors": 0
    }
    
    try:
        # Get posts to process
        posts = posts_to_process if posts_to_process is not None else scraper.get_latest_posts()
        
        if not posts:
            print("No posts to process.")
            # If Telegram is enabled and this is not a test run (real scheduled run)
            if use_telegram and posts_to_process is None:
                try:
                    bot = TelegramBot()
                    await bot.send_no_posts_message()
                except Exception as e:
                    print(f"Error sending 'no posts' message: {str(e)}")
                    stats["errors"] += 1
                    
            # Send the report
            stats["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            stats["duration"] = str(datetime.now() - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S"))
            if report_to:
                await send_run_report(stats, report_to)
            return
            
        print(f"Found {len(posts)} posts to process.")
        stats["total_posts_found"] = len(posts)
        
        # Filter out posts that have already been published (unless in test mode)
        if posts_to_process is None:  # Not in test mode
            new_posts = [post for post in posts if not post.get('is_published', False)]
            if len(new_posts) != len(posts):
                print(f"Filtered out {len(posts) - len(new_posts)} already published posts.")
                stats["filtered_posts"] = len(posts) - len(new_posts)
                posts = new_posts
                
            if not posts:
                print("No new posts to send to Telegram.")
                # If Telegram is enabled, send a message that no new posts were found
                if use_telegram:
                    try:
                        bot = TelegramBot()
                        await bot.send_no_posts_message()
                    except Exception as e:
                        print(f"Error sending 'no posts' message: {str(e)}")
                        stats["errors"] += 1
                
                # Send the report
                stats["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                stats["duration"] = str(datetime.now() - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S"))
                if report_to:
                    await send_run_report(stats, report_to)
                return
        
        # Initialize Telegram bot if needed
        bot = None
        if use_telegram:
            try:
                bot = TelegramBot()
                print("Telegram bot initialized successfully.")
            except Exception as e:
                print(f"Could not initialize Telegram bot: {str(e)}")
                use_telegram = False
                stats["errors"] += 1
                
        # Process each post
        for post in posts:
            # Save post locally
            post_files = save_post_locally(post)
            stats["posts_processed"] += 1
            
            # Try sending to Telegram if enabled
            telegram_success = False
            if use_telegram and bot:
                try:
                    print(f"Attempting to send post to Telegram: {post['title']}")
                    telegram_success = await bot.send_post(post)
                    if telegram_success:
                        print(f"Successfully sent post to Telegram: {post['title']}")
                        stats["posts_sent"] += 1
                        # Mark as published
                        scraper.mark_as_published(post)
                except Exception as e:
                    print(f"Error sending to Telegram: {str(e)}")
                    stats["errors"] += 1
            
            # If we should delete after processing and the post was sent successfully
            if delete_after_processing and telegram_success and post_files:
                try:
                    # Delete the files
                    for file_path in post_files:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            print(f"Deleted file after processing: {file_path}")
                except Exception as e:
                    print(f"Error deleting files: {str(e)}")
                    stats["errors"] += 1
            
            # If either saved locally or sent to Telegram, mark as processed
            scraper.mark_as_parsed(post)
            print(f"Successfully processed post: {post['title']}")
            
            # Update the last processed post URL in checkpoint
            storage.set_checkpoint('last_post_url', post['post_url'])
            storage.set_checkpoint('last_post_title', post['title'])
            storage.set_checkpoint('last_processed_time', datetime.now().isoformat())
    
    except Exception as e:
        print(f"Error processing posts: {str(e)}")
        stats["errors"] += 1
    
    # Send the run report after every run
    stats["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats["duration"] = str(datetime.now() - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S"))
    if report_to:
        await send_run_report(stats, report_to)

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
    Run setup and verification steps
    """
    try:
        # Test Telegram connection if enabled
        if use_telegram:
            telegram_success = await test_telegram_connection(silent)
            if not telegram_success:
                print("Could not connect to Telegram. Make sure your bot token and channel ID are correct.")
                print("Will continue without Telegram integration.")
                use_telegram = False
        
        # Process posts from the website
        await process_posts(use_telegram=use_telegram, report_to=report_to)
    
    except Exception as e:
        print(f"Error in run_setup: {str(e)}")

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
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Shorpy Scraper - fetch and post historic photos')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--silent', '-s', action='store_true', help='Suppress console output')
    parser.add_argument('--run-once', action='store_true', help='Run once and exit')
    parser.add_argument('--daemon', action='store_true', help='Run as a daemon with scheduling')
    parser.add_argument('--check-only', action='store_true', help='Check for new posts but don\'t post to Telegram')
    parser.add_argument('--send-test', action='store_true', help='Send a test message to Telegram')
    parser.add_argument('--last-10-posts', action='store_true', help='Send last 10 posts to Telegram')
    parser.add_argument('--send-button', action='store_true', help='Send a button to Telegram channel to get last 10 posts')
    parser.add_argument('--interactive', action='store_true', help='Enable interactive mode')
    parser.add_argument('--create-index', action='store_true', help='Create an index.html file of all posts')
    parser.add_argument('--validate', action='store_true', help='Validate your setup')
    parser.add_argument('--install', action='store_true', help='Install the script')
    parser.add_argument('--api-server', action='store_true', help='Run the monitoring API server')
    parser.add_argument('--api-port', type=int, default=5000, help='Port for the API server')
    parser.add_argument('--api-host', type=str, default='0.0.0.0', help='Host for the API server')
    parser.add_argument('--purge', action='store_true', help='Purge all database entries')
    return parser.parse_args()

async def main():
    """Main entry point for the script."""
    
    # Parse command line arguments
    args = parse_args()
    
    # Enable verbose logging if requested
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
        logger.debug(f"Python version: {sys.version}")
        logger.debug(f"Current working directory: {os.getcwd()}")
        logger.debug(f"Environment variables: TELEGRAM_BOT_TOKEN: {'set' if os.getenv('TELEGRAM_BOT_TOKEN') else 'not set'}, TELEGRAM_CHANNEL_ID: {'set' if os.getenv('TELEGRAM_CHANNEL_ID') else 'not set'}")
        logger.debug(f"Output directory: {OUTPUT_DIR}")
        logger.debug(f"Temp directory: {TEMP_DIR}")
    
    # Check if interactive mode is requested
    if args.interactive:
        from src.bot.telegram_bot import run_bot
        run_bot()
        return
    
    # Run API server if requested
    if args.api_server:
        from src.api.stats import run_api_server
        logger.info(f"Starting API server on {args.api_host}:{args.api_port}")
        run_api_server(host=args.api_host, port=args.api_port)
        return
    
    # Initialize Telegram bot if credentials are available
    bot = None
    try:
        bot = await run_setup(args.silent)
    except Exception as e:
        logger.error(f"Error setting up Telegram: {str(e)}")
        bot = None
    
    # Process special commands
    if args.purge:
        logger.info("Purging all database entries")
        storage.purge_database()
        return
    
    if args.checkpoint:
        last_post = storage.get_checkpoint("last_post_url")
        title = storage.get_checkpoint("last_post_title")
        timestamp = storage.get_checkpoint("last_processed")
        
        logger.info("\nCheckpoint Information:")
        logger.info(f"Last processed post: {title}")
        logger.info(f"URL: {last_post}")
        logger.info(f"Processed at: {timestamp}")
        logger.info(f"Total posts processed: {storage.count_parsed_posts()}")
        return
    
    if args.test_posts:
        num_posts = int(args.test_posts)
        logger.info(f"Test mode: Processing {num_posts} posts")
        scraper = ShorpyScraper()
        test_posts = scraper.get_test_posts(num_posts)
        
        logger.info(f"Found {len(test_posts)} test posts")
        
        for post in test_posts:
            logger.info(f"Post: {post['title']}")
            # Save locally
            storage.save_post(post)
            # Send to Telegram
            if bot:
                await bot.send_post(post)
            
            # Delete files if requested
            if args.delete_files:
                storage.delete_post_files(post)
        
        return
    
    # Send the last 10 posts if requested
    if args.last_10_posts and bot:
        await bot.send_last_10_posts()
        return
    
    # Send a button to show the last 10 posts if requested
    if args.send_button and bot:
        await bot.send_latest_posts_button()
        return
    
    # Regular operation - process posts
    scraper = ShorpyScraper()
    
    # Schedule mode
    if args.daemon:
        import schedule
        
        # Setup scheduled job
        def job():
            asyncio.run(process_posts(args, bot, scraper))
        
        # Run job immediately
        logger.info("Running initial job...")
        asyncio.run(process_posts(args, bot, scraper))
        
        # Schedule job to run every 12 hours
        schedule.every(12).hours.do(job)
        
        logger.info("Scheduled to run every 12 hours...")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Shutting down...")
    
    # Run once mode
    else:
        await process_posts(args, bot, scraper)
        
        if args.run_once:
            logger.info("Run-once mode enabled, exiting.")
        else:
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