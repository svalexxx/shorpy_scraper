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
from scraper import ShorpyScraper
from telegram_bot import TelegramBot
from models import storage

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

async def process_posts(use_telegram=True, posts_to_process=None, delete_after_processing=False):
    scraper = ShorpyScraper()
    
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
            return
            
        print(f"Found {len(posts)} posts to process.")
        
        # Filter out posts that have already been published (unless in test mode)
        if posts_to_process is None:  # Not in test mode
            new_posts = [post for post in posts if not post.get('is_published', False)]
            if len(new_posts) != len(posts):
                print(f"Filtered out {len(posts) - len(new_posts)} already published posts.")
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
                
        # Process each post
        for post in posts:
            # Save post locally
            post_files = save_post_locally(post)
            
            # Try sending to Telegram if enabled
            telegram_success = False
            if use_telegram and bot:
                try:
                    print(f"Attempting to send post to Telegram: {post['title']}")
                    telegram_success = await bot.send_post(post)
                    if telegram_success:
                        print(f"Successfully sent post to Telegram: {post['title']}")
                        # Mark as published
                        scraper.mark_as_published(post)
                except Exception as e:
                    print(f"Error sending to Telegram: {str(e)}")
            
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
            
            # If either saved locally or sent to Telegram, mark as processed
            scraper.mark_as_parsed(post)
            print(f"Successfully processed post: {post['title']}")
            
            # Update the last processed post URL in checkpoint
            storage.set_checkpoint('last_post_url', post['post_url'])
            storage.set_checkpoint('last_post_title', post['title'])
            storage.set_checkpoint('last_processed_time', datetime.now().isoformat())
    
    except Exception as e:
        print(f"Error processing posts: {str(e)}")

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

async def run_setup(silent=False):
    # Test Telegram connection
    try:
        print("Testing Telegram connection...")
        connection_ok = await test_telegram_connection(silent)
        
        if not connection_ok:
            print("Telegram connection test failed. Posts will only be saved locally.")
            print("To enable Telegram posting:")
            print("1. Make sure your bot token is correct")
            print("2. Create a channel and add the bot as an administrator")
            print("3. Get the correct channel ID and update .env file")
            return False
        
        print("Telegram connection test successful!")
        return True
    except Exception as e:
        print(f"Setup error: {str(e)}")
        return False

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

async def process_test_posts(num_posts=2, delete_after_processing=False):
    """Process a specific number of posts for testing purposes."""
    scraper = ShorpyScraper()
    
    try:
        # Get test posts
        posts = scraper.get_test_posts(num_posts)
        
        if not posts:
            print("No test posts found.")
            return
        
        print(f"Processing {len(posts)} test posts...")
        await process_posts(use_telegram=True, posts_to_process=posts, delete_after_processing=delete_after_processing)
        print(f"Completed processing test posts.")
    except Exception as e:
        print(f"Error processing test posts: {str(e)}")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Shorpy Scraper and Telegram Bot')
    parser.add_argument('--reprocess', action='store_true', help='Reprocess existing posts')
    parser.add_argument('--channel', type=str, help='Override channel ID in .env file')
    parser.add_argument('--schedule', action='store_true', help='Run on a schedule (every 12 hours)')
    parser.add_argument('--run-once', action='store_true', help='Run once and exit')
    parser.add_argument('--delete-files', action='store_true', help='Delete local files after sending them to Telegram')
    parser.add_argument('--purge', action='store_true', help='Purge all files in the scraped_posts directory')
    parser.add_argument('--checkpoint', action='store_true', help='Display checkpoint information')
    parser.add_argument('--test-posts', type=int, nargs='?', const=2, help='Process a specific number of posts for testing (default: 2)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--silent', action='store_true', help='Skip sending test message on startup (for production)')
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    print("Starting Shorpy Scraper...")
    
    # Print environment info in verbose mode
    if args.verbose:
        logger.debug(f"Python version: {sys.version}")
        logger.debug(f"Current working directory: {os.getcwd()}")
        logger.debug(f"Environment variables: TELEGRAM_BOT_TOKEN: {'set' if os.getenv('TELEGRAM_BOT_TOKEN') else 'not set'}, TELEGRAM_CHANNEL_ID: {'set' if os.getenv('TELEGRAM_CHANNEL_ID') else 'not set'}")
        logger.debug(f"Output directory: {OUTPUT_DIR}")
        logger.debug(f"Temp directory: {TEMP_DIR}")
    
    # Check if user wants to see checkpoint information
    if args.checkpoint:
        print_checkpoint_info()
        return
    
    # Check if user wants to purge all scraped files
    if args.purge:
        purge_scraped_files()
        clean_temp_images()
        return
    
    # Set environment variable for reprocessing if --reprocess flag is used
    if args.reprocess:
        os.environ['REPROCESS_POSTS'] = 'true'
        print("Reprocessing mode enabled")
    
    # Set environment variable for deleting files if --delete-files flag is used
    if args.delete_files:
        os.environ['DELETE_AFTER_PROCESSING'] = 'true'
        print("Delete after processing enabled")
    
    # Override channel ID if provided
    if args.channel:
        os.environ['TELEGRAM_CHANNEL_ID'] = args.channel
        print(f"Using override channel ID: {args.channel}")
    
    # Run setup and connection test
    telegram_ok = asyncio.run(run_setup(args.silent))
    
    # Process test posts if requested
    if args.test_posts is not None:
        print(f"Test mode enabled: Processing {args.test_posts} posts...")
        asyncio.run(process_test_posts(args.test_posts, args.delete_files))
        print_checkpoint_info()
        create_index_html()
        clean_temp_images()
        return
    
    # Always proceed even if Telegram is not working
    # We'll save posts locally
    
    if args.schedule:
        # Schedule the job to run every 12 hours
        schedule.every(12).hours.do(job)
        print("Job scheduled to run every 12 hours.")
    
    # Run immediately on startup
    print("Running initial job...")
    job()
    
    # Print checkpoint info after processing
    print_checkpoint_info()
    
    # Create index.html to browse saved posts
    create_index_html()
    
    # If run-once flag is set, exit now
    if args.run_once:
        print("Run-once mode enabled, exiting.")
        clean_temp_images()
        return
    
    # Keep the script running if schedule mode is enabled
    if args.schedule:
        print("Bot is now running. Press Ctrl+C to stop.")
        print(f"Scraped posts are being saved to the '{OUTPUT_DIR}' directory.")
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            print("Scraper stopped. Creating final index.html...")
            create_index_html()
            print_checkpoint_info()
            clean_temp_images()
            print("Done.")
    else:
        print("Job completed. Exiting.")
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
    main() 