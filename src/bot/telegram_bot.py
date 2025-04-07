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
from datetime import datetime, timedelta
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
    def __init__(self, channel_id=None):
        """Initialize the Telegram bot.
        
        Args:
            channel_id: Optional override for the channel ID
        """
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.channel_id = channel_id or os.getenv("TELEGRAM_CHANNEL_ID")
        self.report_channel_id = os.getenv("TELEGRAM_REPORT_CHANNEL_ID", self.channel_id)
        self.logger = logging.getLogger(__name__)
        
        if not self.bot_token:
            raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable")
        if not self.channel_id:
            raise ValueError("Missing TELEGRAM_CHANNEL_ID environment variable")
        
        # Initialize the bot
        self.bot = Bot(token=self.bot_token)
        self.logger.info(f"Telegram bot initialized with channel ID: {self.channel_id}")
        if self.report_channel_id != self.channel_id:
            self.logger.info(f"Reports will be sent to separate channel ID: {self.report_channel_id}")
        
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
                self.logger.info("Testing Telegram connection in silent mode")
                # Just verify the bot info without sending a message
                me = await self.bot.get_me()
                self.logger.info(f"Connected to Telegram as {me.username}")
                return True
                
            self.logger.info("Testing Telegram connection by sending a test message")
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=f"🔄 Connection test successful! (Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            )
            self.logger.info("Test message sent successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error testing Telegram connection: {str(e)}")
            return False
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_no_posts_message(self, send_detailed_report=False, send_notification=True):
        """Send a message indicating that no new posts were found.
        
        Args:
            send_detailed_report: Whether to send a detailed report to the report channel
            send_notification: Whether to send a notification to the main channel
            
        Returns:
            bool: True if the message was sent successfully, False otherwise
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Send to main channel if requested
            if send_notification:
                self.logger.info("Sending 'no new posts' notification to channel")
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=f"📝 No new posts found at {now}.\nWill check again on the next run."
                )
            else:
                self.logger.info("Skipping 'no new posts' notification to channel")
            
            # Send detailed report only if requested
            if send_detailed_report:
                self.logger.info("Sending detailed report to report channel")
                # Send detailed report to report channel
                stats = {
                    "start_time": now,
                    "end_time": now,
                    "duration": "0:00:01",
                    "total_posts_found": 0,
                    "posts_processed": 0,
                    "posts_sent": 0,
                    "warnings": ["No new posts found during this check"]
                }
                
                # Get database stats
                try:
                    cursor = db_pool.execute("SELECT COUNT(*) FROM posts")
                    stats["total_posts"] = cursor.fetchone()[0]
                    
                    cursor = db_pool.execute("SELECT COUNT(*) FROM posts WHERE published = 1")
                    stats["published_posts"] = cursor.fetchone()[0]
                    
                    # Get posts from last 24 hours
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor = db_pool.execute("SELECT COUNT(*) FROM posts WHERE timestamp > ?", (yesterday,))
                    stats["posts_last_24h"] = cursor.fetchone()[0]
                except Exception as e:
                    self.logger.error(f"Error getting database stats: {str(e)}")
                
                # Get disk usage
                try:
                    stats["disk_usage"] = {}
                    
                    # Database size
                    db_path = os.path.join(os.getcwd(), "shorpy.db")
                    if os.path.exists(db_path):
                        db_size = os.path.getsize(db_path) / (1024 * 1024)  # Convert to MB
                        stats["disk_usage"]["db_size_mb"] = round(db_size, 2)
                    
                    # Scraped posts size
                    posts_dir = os.path.join(os.getcwd(), "scraped_posts")
                    if os.path.exists(posts_dir):
                        size = 0
                        file_count = 0
                        for path, dirs, files in os.walk(posts_dir):
                            for f in files:
                                fp = os.path.join(path, f)
                                size += os.path.getsize(fp)
                                file_count += 1
                        
                        size_mb = size / (1024 * 1024)  # Convert to MB
                        stats["disk_usage"]["scraped_posts_size_mb"] = round(size_mb, 2)
                        stats["disk_usage"]["scraped_posts_file_count"] = file_count
                except Exception as e:
                    self.logger.error(f"Error getting disk usage: {str(e)}")
                
                await self.send_status_report(stats)
            
            if send_notification or send_detailed_report:
                self.logger.info("No posts message and/or report sent successfully")
                return True
            else:
                self.logger.info("No messages were sent (both notification and report were disabled)")
                return False
                
        except Exception as e:
            self.logger.error(f"Error sending 'no posts' message: {str(e)}")
            return False
            
    async def download_image(self, image_url: str) -> Optional[str]:
        """Download an image and save it to a temporary file.
        
        Args:
            image_url: URL of the image to download
            
        Returns:
            Optional[str]: Path to the downloaded image or None if failed
        """
        try:
            self.logger.info(f"Downloading image from {image_url}")
            response = requests.get(image_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", dir="temp_images")
            
            # Save the image to the temporary file
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
                
            temp_file.close()
            self.logger.info(f"Image downloaded successfully to {temp_file.name}")
            return temp_file.name
        except Exception as e:
            self.logger.error(f"Error downloading image: {str(e)}")
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
                    self.logger.info(f"Sending post with image: {post['title']}")
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
                        self.logger.info(f"Deleted temporary file: {image_path}")
                    except Exception as e:
                        self.logger.warning(f"Could not delete temporary file {image_path}: {str(e)}")
                        
                    self.logger.info(f"Post sent successfully: {post['title']}")
                    return True
                else:
                    # If image download failed, send just the text
                    self.logger.warning(f"Image download failed, sending text only for: {post['title']}")
                    await self.bot.send_message(
                        chat_id=self.channel_id,
                        text=f"{caption}\n\n(Image could not be downloaded)",
                        parse_mode='HTML'
                    )
                    return True
            else:
                # No image URL, send just the text
                self.logger.info(f"Sending post without image: {post['title']}")
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=caption,
                    parse_mode='HTML'
                )
                return True
                
        except Exception as e:
            self.logger.error(f"Error sending post to Telegram: {str(e)}")
            # Try one more time with just the text if sending with image failed
            try:
                if 'image_url' in post and post['image_url']:
                    self.logger.info("Retrying with text only")
                    await self.bot.send_message(
                        chat_id=self.channel_id,
                        text=f"{caption}\n\n(Image could not be sent)",
                        parse_mode='HTML'
                    )
                    return True
            except Exception as retry_error:
                self.logger.error(f"Error in retry attempt: {str(retry_error)}")
                
            return False
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_status_report(self, stats, recipient=None):
        """
        Send a status report with statistics.
        
        Args:
            stats: Dictionary containing run statistics
            recipient: Optional chat ID or username to send report to
        
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            # Format report message
            message = self._format_status_report(stats)
            
            # Determine recipient
            chat_id = self.channel_id  # Default to channel
            
            if recipient:
                # Handle different recipient formats
                if isinstance(recipient, str):
                    # Strip any @ symbol if present, telegram can handle usernames with or without it
                    recipient = recipient.lstrip('@')
                    
                    if recipient.lower().endswith('bot'):
                        # It's a bot - we'll try sending to it anyway, even though Telegram docs
                        # say bots can't receive messages from other bots, it sometimes works
                        self.logger.info(f"Attempting to send report to bot: @{recipient}")
                        chat_id = recipient
                    elif recipient.startswith('-100'):
                        # It's a channel ID
                        try:
                            chat_id = int(recipient)
                        except ValueError:
                            chat_id = recipient
                    else:
                        # Try to handle as a username
                        try:
                            # See if it's a numeric ID
                            chat_id = int(recipient)
                        except ValueError:
                            # Assume it's a username
                            chat_id = f"@{recipient}"
                else:
                    # If it's already a number (int), use directly
                    chat_id = recipient
                
                self.logger.info(f"Sending report to specific recipient: {chat_id}")
            
            # Send message as plain text
            await self.bot.send_message(chat_id=chat_id, text=message)
            self.logger.info(f"Status report sent successfully to {chat_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending status report: {str(e)}")
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
            self.logger.info("Sending 'latest posts' button message")
            
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
            
            self.logger.info("'Latest posts' button message sent successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error sending 'latest posts' button message: {str(e)}")
            return False

    async def get_last_10_posts(self) -> List[Dict[str, Any]]:
        """Get the last 10 posts from the database.
        
        Returns:
            List[Dict[str, Any]]: List of posts with their details
        """
        try:
            self.logger.info("Fetching last 10 posts from database")
            
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
            
            self.logger.info(f"Found {len(posts)} posts in database")
            return posts
            
        except Exception as e:
            self.logger.error(f"Error fetching last 10 posts: {str(e)}")
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
                    self.logger.error(f"Failed to send post: {post['title']}")
            
            # Send a final message
            await self.bot.send_message(
                chat_id=self.channel_id,
                text="End of the last posts list. Visit https://shorpy.com for more historic photos."
            )
            
            return True
        
        except Exception as e:
            self.logger.error(f"Error sending last 10 posts: {str(e)}")
            return False

    def _format_status_report(self, stats):
        """Format a status report message with the provided statistics.
        
        Args:
            stats: Dictionary containing statistics to report
            
        Returns:
            str: Formatted message text
        """
        # Build the message
        message = f"📊 Shorpy Scraper Status Report\n\n"
        
        # Add environment indicator
        env_type = "Production" if str(self.channel_id).startswith("-100") else "Development"
        message += f"Environment: {env_type}\n\n"
        
        # Run stats section
        if "start_time" in stats:
            message += f"Run Information:\n"
            message += f"• Start time: {stats['start_time']}\n"
            if "end_time" in stats:
                message += f"• End time: {stats['end_time']}\n"
            if "duration" in stats:
                message += f"• Duration: {stats['duration']}\n"
            message += "\n"
        
        # Posts section
        message += f"Posts:\n"
        if "total_posts_found" in stats:
            message += f"• Total posts found: {stats['total_posts_found']}\n"
        if "posts_processed" in stats:
            message += f"• Posts processed: {stats['posts_processed']}\n"
        if "posts_sent" in stats:
            message += f"• Posts sent to Telegram: {stats['posts_sent']}\n"
        message += "\n"
        
        # Database stats
        if "total_posts" in stats:
            message += f"Database:\n"
            message += f"• Total posts: {stats['total_posts']}\n"
            if "published_posts" in stats:
                message += f"• Published posts: {stats['published_posts']}\n"
            if "posts_last_24h" in stats:
                message += f"• Posts in last 24h: {stats['posts_last_24h']}\n"
            message += "\n"
        
        # System information
        if "disk_usage" in stats:
            message += f"System:\n"
            disk = stats["disk_usage"]
            if "db_size_mb" in disk:
                message += f"• Database size: {disk['db_size_mb']} MB\n"
            if "scraped_posts_size_mb" in disk:
                message += f"• Scraped posts: {disk['scraped_posts_size_mb']} MB\n"
            if "scraped_posts_file_count" in disk:
                message += f"• Saved files: {disk['scraped_posts_file_count']}\n"
            message += "\n"
        
        # Warning information - added before error information to match format        
        if "warnings" in stats and stats["warnings"]:
            message += f"⚠️ Warnings:\n"
            for warning in stats["warnings"]:
                message += f"• {warning}\n"
            message += "\n"
        
        # Error information
        if "errors" in stats and stats["errors"] > 0:
            message += f"⚠️ Errors: {stats['errors']}\n"
            if "recent_errors" in stats and stats["recent_errors"]:
                for i, error in enumerate(stats["recent_errors"][:3], 1):
                    short_error = error[-100:] if len(error) > 100 else error
                    message += f"• {short_error}\n"
                message += "\n"
        
        # Add timestamp without HTML tags
        message += f"Report time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message

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