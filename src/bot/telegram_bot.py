import os
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError, NetworkError, TimedOut
from dotenv import load_dotenv
import logging
import requests
import tempfile
import uuid
from typing import Dict, Any, Optional, List, Union, Tuple
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.database.connection import db_pool

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Use the same temp directory as main.py
TEMP_DIR = "temp_images"
os.makedirs(TEMP_DIR, exist_ok=True)

class TelegramBot:
    def __init__(self) -> None:
        """Initialize the Telegram bot with credentials from environment variables."""
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
        self.report_channel_id = os.getenv('TELEGRAM_REPORT_CHANNEL_ID', self.channel_id)
        
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN not set in environment variables")
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
            
        if not self.channel_id:
            logger.error("TELEGRAM_CHANNEL_ID not set in environment variables")
            raise ValueError("TELEGRAM_CHANNEL_ID not set")
        
        self.bot = Bot(token=self.token)
        logger.info(f"Telegram bot initialized with channel ID: {self.channel_id}")
        if self.report_channel_id != self.channel_id:
            logger.info(f"Reports will be sent to separate channel ID: {self.report_channel_id}")
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def test_connection(self, silent: bool = False) -> bool:
        """Test the connection to Telegram.
        
        Args:
            silent: If True, skips sending a test message
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if silent:
                logger.info("Testing Telegram connection in silent mode")
                # Just verify the bot info without sending a message
                me = await self.bot.get_me()
                logger.info(f"Connected to Telegram as {me.username}")
                return True
                
            logger.info("Testing Telegram connection by sending a test message")
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=f"🔄 Connection test successful! (Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            )
            logger.info("Test message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Error testing Telegram connection: {str(e)}")
            return False
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_no_posts_message(self) -> bool:
        """Send a message when no new posts are found.
        
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            logger.info("Sending 'no new posts' notification")
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Send to main channel
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=f"📝 No new posts found at {now}.\nWill check again on the next run."
            )
            
            # Send detailed report to report channel
            stats = {
                "start_time": now,
                "total_posts_found": 0,
                "posts_processed": 0,
                "posts_sent": 0,
                "warnings": ["No new posts found during this check"],
                "disk_usage": {
                    "db_size_mb": 0,
                    "scraped_posts_size_mb": 0,
                    "scraped_posts_file_count": 0
                }
            }
            
            # Get database stats
            try:
                with db_pool.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get total posts
                    cursor.execute("SELECT COUNT(*) FROM parsed_posts")
                    stats["total_posts"] = cursor.fetchone()[0]
                    
                    # Get published posts count
                    cursor.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
                    stats["published_posts"] = cursor.fetchone()[0]
                    
                    # Get posts in last 24h
                    cursor.execute("""
                        SELECT COUNT(*) FROM parsed_posts 
                        WHERE published = 1 
                        AND parsed_at >= datetime('now', '-1 day')
                    """)
                    stats["posts_last_24h"] = cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"Error getting database stats: {str(e)}")
            
            # Get disk usage
            try:
                if os.path.exists("shorpy_data.db"):
                    stats["disk_usage"]["db_size_mb"] = round(os.path.getsize("shorpy_data.db") / (1024 * 1024), 2)
                
                if os.path.exists("scraped_posts"):
                    total_size = 0
                    file_count = 0
                    for dirpath, dirnames, filenames in os.walk("scraped_posts"):
                        for f in filenames:
                            fp = os.path.join(dirpath, f)
                            total_size += os.path.getsize(fp)
                            file_count += 1
                    stats["disk_usage"]["scraped_posts_size_mb"] = round(total_size / (1024 * 1024), 2)
                    stats["disk_usage"]["scraped_posts_file_count"] = file_count
            except Exception as e:
                logger.error(f"Error getting disk usage: {str(e)}")
            
            await self.send_status_report(stats)
            
            logger.info("'No new posts' notification and report sent successfully")
            return True
        except Exception as e:
            logger.error(f"Error sending 'no new posts' message: {str(e)}")
            return False
            
    async def download_image(self, image_url: str) -> Optional[str]:
        """Download an image and save it to a temporary file.
        
        Args:
            image_url: URL of the image to download
            
        Returns:
            Optional[str]: Path to the downloaded image or None if failed
        """
        try:
            logger.info(f"Downloading image from {image_url}")
            response = requests.get(image_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", dir="temp_images")
            
            # Save the image to the temporary file
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
                
            temp_file.close()
            logger.info(f"Image downloaded successfully to {temp_file.name}")
            return temp_file.name
        except Exception as e:
            logger.error(f"Error downloading image: {str(e)}")
            return None
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_post(self, post: Dict[str, Any]) -> bool:
        """Send a post to the Telegram channel.
        
        Args:
            post: Dictionary containing post data
            
        Returns:
            bool: True if post was sent successfully, False otherwise
        """
        caption = f"<b>{post['title']}</b>\n\n{post['description']}\n\n<a href=\"{post['post_url']}\">View on Shorpy</a>"
        
        # Truncate caption if it's too long (Telegram limit is 1024 chars)
        if len(caption) > 1024:
            caption = caption[:1020] + "..."
            
        try:
            if post['image_url']:
                # Download the image first
                image_path = await self.download_image(post['image_url'])
                
                if image_path:
                    logger.info(f"Sending post with image: {post['title']}")
                    # Send the image with caption
                    with open(image_path, 'rb') as img_file:
                        await self.bot.send_photo(
                            chat_id=self.channel_id,
                            photo=img_file,
                            caption=caption,
                            parse_mode='HTML'
                        )
                        
                    # Delete the temporary file
                    try:
                        os.unlink(image_path)
                        logger.info(f"Deleted temporary file: {image_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete temporary file {image_path}: {str(e)}")
                        
                    logger.info(f"Post sent successfully: {post['title']}")
                    return True
                else:
                    # If image download failed, send just the text
                    logger.warning(f"Image download failed, sending text only for: {post['title']}")
                    await self.bot.send_message(
                        chat_id=self.channel_id,
                        text=f"{caption}\n\n(Image could not be downloaded)",
                        parse_mode='HTML'
                    )
                    return True
            else:
                # No image URL, send just the text
                logger.info(f"Sending post without image: {post['title']}")
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=caption,
                    parse_mode='HTML'
                )
                return True
                
        except Exception as e:
            logger.error(f"Error sending post to Telegram: {str(e)}")
            # Try one more time with just the text if sending with image failed
            try:
                if 'image_url' in post and post['image_url']:
                    logger.info("Retrying with text only")
                    await self.bot.send_message(
                        chat_id=self.channel_id,
                        text=f"{caption}\n\n(Image could not be sent)",
                        parse_mode='HTML'
                    )
                    return True
            except Exception as retry_error:
                logger.error(f"Error in retry attempt: {str(retry_error)}")
                
            return False
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_status_report(self, stats: Dict[str, Any], recipient: Optional[str] = None) -> bool:
        """Send a status report to the Telegram channel or to a specific recipient.
        
        Args:
            stats: Dictionary containing statistics to report
            recipient: Optional username or chat ID to send report to (e.g., @username)
            
        Returns:
            bool: True if report was sent successfully, False otherwise
        """
        try:
            logger.info("Sending status report")
            
            # Determine target chat ID
            target_chat_id = self.report_channel_id
            if recipient:
                # If recipient starts with @, it's a username - we can't send to bots
                if recipient.startswith('@'):
                    logger.warning(f"Cannot send report to bot username {recipient}. Using configured report channel.")
                else:
                    # Try to use the recipient as a chat ID
                    try:
                        target_chat_id = int(recipient)
                        logger.info(f"Sending report to chat ID: {target_chat_id}")
                    except ValueError:
                        logger.warning(f"Invalid chat ID format: {recipient}. Using configured report channel.")
            
            # Build the message
            message = f"📊 <b>Shorpy Scraper Status Report</b>\n\n"
            
            # Add environment indicator
            env_type = "Production" if self.channel_id.startswith("-100") else "Development"
            message += f"<b>Environment:</b> {env_type}\n\n"
            
            # Run stats section
            if "start_time" in stats:
                message += f"<b>Run Information:</b>\n"
                message += f"• Start time: {stats['start_time']}\n"
                if "end_time" in stats:
                    message += f"• End time: {stats['end_time']}\n"
                if "duration" in stats:
                    message += f"• Duration: {stats['duration']}\n"
                message += "\n"
            
            # Posts section
            message += f"<b>Posts:</b>\n"
            if "total_posts_found" in stats:
                message += f"• Total posts found: {stats['total_posts_found']}\n"
            if "filtered_posts" in stats:
                message += f"• Already published posts: {stats['filtered_posts']}\n"
            if "posts_processed" in stats:
                message += f"• Posts processed: {stats['posts_processed']}\n"
            if "posts_sent" in stats:
                message += f"• Posts sent to Telegram: {stats['posts_sent']}\n"
            
            # Database stats
            if "total_posts" in stats:
                message += f"\n<b>Database:</b>\n"
                message += f"• Total posts: {stats['total_posts']}\n"
                if "published_posts" in stats:
                    message += f"• Published posts: {stats['published_posts']}\n"
                if "posts_last_24h" in stats:
                    message += f"• Posts in last 24h: {stats['posts_last_24h']}\n"
            
            # System information
            if "disk_usage" in stats:
                message += f"\n<b>System:</b>\n"
                disk = stats["disk_usage"]
                if "db_size_mb" in disk:
                    message += f"• Database size: {disk['db_size_mb']} MB\n"
                if "scraped_posts_size_mb" in disk:
                    message += f"• Scraped posts: {disk['scraped_posts_size_mb']} MB\n"
                if "scraped_posts_file_count" in disk:
                    message += f"• Saved files: {disk['scraped_posts_file_count']}\n"
            
            # Error information
            if "errors" in stats and stats["errors"] > 0:
                message += f"\n<b>⚠️ Errors:</b> {stats['errors']}\n"
                if "recent_errors" in stats:
                    message += "Most recent errors:\n"
                    for i, error in enumerate(stats["recent_errors"][:3], 1):
                        short_error = error[-100:] if len(error) > 100 else error
                        message += f"  {i}. {short_error}\n"
            
            # Warning information        
            if "warnings" in stats and stats["warnings"]:
                message += f"\n<b>⚠️ Warnings:</b>\n"
                for warning in stats["warnings"]:
                    message += f"• {warning}\n"
            
            # Add timestamp
            message += f"\nReport time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Send the message
            await self.bot.send_message(
                chat_id=target_chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info(f"Status report sent successfully to chat ID: {target_chat_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending status report: {str(e)}")
            return False 

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_latest_posts_button(self) -> bool:
        """Send a message with a button to retrieve the last 10 posts.
        
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            logger.info("Sending 'latest posts' button message")
            
            # Create an inline keyboard with a button
            keyboard = [
                [InlineKeyboardButton("Show Last 10 Posts", callback_data="show_last_10_posts")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send message with button
            await self.bot.send_message(
                chat_id=self.channel_id,
                text="📸 Click the button below to see the last 10 Shorpy posts:",
                reply_markup=reply_markup
            )
            
            logger.info("'Latest posts' button message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Error sending 'latest posts' button message: {str(e)}")
            return False

    async def get_last_10_posts(self) -> List[Dict[str, Any]]:
        """Get the last 10 posts from the database.
        
        Returns:
            List[Dict[str, Any]]: List of posts with their details
        """
        try:
            logger.info("Fetching last 10 posts from database")
            
            cursor = db_pool.execute(
                """
                SELECT post_url, title, image_url, description, parsed_at 
                FROM parsed_posts 
                WHERE published = 1
                ORDER BY parsed_at DESC LIMIT 10
                """
            )
            
            posts = []
            for row in cursor.fetchall():
                posts.append({
                    'post_url': row[0],
                    'title': row[1],
                    'image_url': row[2],
                    'description': row[3],
                    'parsed_at': row[4],
                    'is_published': True
                })
            
            logger.info(f"Found {len(posts)} posts in database")
            return posts
            
        except Exception as e:
            logger.error(f"Error fetching last 10 posts: {str(e)}")
            return []

    async def send_last_10_posts(self) -> bool:
        """Send the last 10 posts to the Telegram channel.
        
        Returns:
            bool: True if all posts were sent successfully, False otherwise
        """
        try:
            posts = await self.get_last_10_posts()
            
            if not posts:
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text="No posts found in the database."
                )
                return True
            
            # Send an initial message
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=f"📷 Here are the last {len(posts)} Shorpy posts:"
            )
            
            # Send each post
            for post in posts:
                success = await self.send_post(post)
                if not success:
                    logger.error(f"Failed to send post: {post['title']}")
            
            # Send a final message
            await self.bot.send_message(
                chat_id=self.channel_id,
                text="End of the last posts list. Visit https://shorpy.com for more historic photos."
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error sending last 10 posts: {str(e)}")
            return False

def setup_bot_commands():
    """Set up the bot with command handlers for interactive use."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
        return None
    
    # Create the application
    application = ApplicationBuilder().token(token).build()
    
    # Create a TelegramBot instance for command handling
    bot_instance = TelegramBot()
    
    # Define command handlers
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        await update.message.reply_text(
            "👋 Welcome to the Shorpy Scraper Bot!\n\n"
            "This bot posts historic photos from Shorpy.com to this channel.\n\n"
            "Available commands:\n"
            "/latest - Show the last 10 posts\n"
            "/status - Show the current status\n"
            "/help - Show this help message"
        )
    
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command."""
        await update.message.reply_text(
            "🔍 Shorpy Scraper Bot Help\n\n"
            "Available commands:\n"
            "/latest - Show the last 10 posts\n"
            "/status - Show the current status\n"
            "/help - Show this help message"
        )
    
    async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /latest command."""
        await update.message.reply_text("📸 Fetching the last 10 posts from Shorpy.com...")
        await bot_instance.send_last_10_posts()
    
    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /status command."""
        from src.utils.monitor import get_system_stats
        
        try:
            stats = await get_system_stats()
            await bot_instance.send_status_report(stats)
        except Exception as e:
            logger.error(f"Error in status command: {str(e)}")
            await update.message.reply_text(f"❌ Error getting status: {str(e)}")
    
    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "show_last_10_posts":
            await query.edit_message_text(text="📸 Fetching the last 10 posts from Shorpy.com...")
            await bot_instance.send_last_10_posts()
    
    # Add handlers to the application
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("latest", latest_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    return application

def run_bot():
    """Run the bot in polling mode (for development/testing)."""
    application = setup_bot_commands()
    if application:
        logger.info("Starting bot in polling mode...")
        application.run_polling()
    else:
        logger.error("Could not start bot: application setup failed") 