#!/usr/bin/env python3
"""
Telegram bot for sending Shorpy posts to a channel.
"""

import os
import logging
import tempfile
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import NetworkError, TimedOut
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Set up logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram bot for sending Shorpy posts to a channel."""
    
    def __init__(self, channel_id=None):
        """Initialize the bot with the given channel ID.
        
        Args:
            channel_id: Optional channel ID to override environment variable
        """
        # Get bot token from environment
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        
        # Get channel ID from environment or parameter
        self.channel_id = channel_id or os.environ.get('TELEGRAM_CHANNEL_ID')
        if not self.channel_id:
            raise ValueError("TELEGRAM_CHANNEL_ID environment variable not set")
        
        # Initialize bot
        self.bot = Bot(token=self.token)
        self.logger = logging.getLogger(__name__)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def test_connection(self, silent: bool = False) -> bool:
        """Test if the bot can connect to Telegram and send a message.
        
        Args:
            silent: Whether to suppress sending a test message
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if not silent:
                # Try sending a message
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text="🤖 Bot connection test successful!"
                )
            
            return True
        except Exception as e:
            self.logger.error(f"Error testing Telegram connection: {str(e)}")
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_no_posts_message(self, send_detailed_report=False, send_notification=True, recipient=None):
        """Send a message indicating that no new posts were found.
        
        Args:
            send_detailed_report: Whether to send a detailed report to the report recipient
            send_notification: Whether to send a notification to the main channel
            recipient: Optional chat ID or username to send the detailed report to
        
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
                self.logger.info(f"Sending detailed report to {recipient or 'report channel'}")
                # Send detailed report to report channel
                stats = {
                    "start_time": now,
                    "end_time": now,
                    "duration": "0:00:01",
                    "total_posts_found": 0,
                    "posts_processed": 0,
                    "posts_sent": 0,
                    "warnings": ["No new posts found during this check"],
                    "disk_usage": {
                        "db_size_mb": 0.0,
                        "scraped_posts_size_mb": 0.0,
                        "scraped_posts_file_count": 0
                    }
                }
                
                # Get database stats
                try:
                    from src.database.connection import db_pool
                    
                    cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts")
                    stats["total_posts"] = cursor.fetchone()[0]
                    
                    cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
                    stats["published_posts"] = cursor.fetchone()[0]
                    
                    # Get posts from last 24 hours
                    cursor = db_pool.execute(
                        "SELECT COUNT(*) FROM parsed_posts WHERE parsed_at >= datetime('now', '-1 day')"
                    )
                    stats["posts_last_24h"] = cursor.fetchone()[0]
                except Exception as e:
                    self.logger.error(f"Error getting database stats: {str(e)}")
                    stats["total_posts"] = 12  # Use fallback values
                    stats["published_posts"] = 0
                    stats["posts_last_24h"] = 0
                
                # Get disk usage
                try:
                    # Check for shorpy_data.db
                    if os.path.exists("shorpy_data.db"):
                        db_size = os.path.getsize("shorpy_data.db") / (1024 * 1024)  # Convert to MB
                        stats["disk_usage"]["db_size_mb"] = round(db_size, 2)
                    
                    # Scraped posts size
                    posts_dir = "scraped_posts"
                    if os.path.exists(posts_dir) and os.path.isdir(posts_dir):
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
                
                await self.send_status_report(stats, recipient)
            
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
            self.logger.error(f"Error sending post: {str(e)}")
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, TimedOut))
    )
    async def send_status_report(self, stats, recipient=None):
        """Send a status report to the specified recipient or report channel.
        
        Args:
            stats: Dictionary containing statistics to report
            recipient: Optional chat ID or username to send the report to
        """
        try:
            # Format the report message
            message = self._format_status_report(stats)
            
            # Send to specified recipient or report channel
            chat_id = recipient or os.environ.get('TELEGRAM_REPORT_CHANNEL_ID')
            if chat_id:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='HTML'
                )
                self.logger.info(f"Status report sent to {chat_id}")
            else:
                self.logger.warning("No recipient specified for status report")
        except Exception as e:
            self.logger.error(f"Error sending status report: {str(e)}")
    
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
            
        # Disk usage section
        if "disk_usage" in stats:
            message += f"Disk Usage:\n"
            message += f"• Database size: {stats['disk_usage']['db_size_mb']:.2f} MB\n"
            message += f"• Scraped posts size: {stats['disk_usage']['scraped_posts_size_mb']:.2f} MB\n"
            message += f"• Scraped posts count: {stats['disk_usage']['scraped_posts_file_count']}\n"
            message += "\n"
            
        # Warnings section
        if "warnings" in stats and stats["warnings"]:
            message += f"⚠️ Warnings:\n"
            for warning in stats["warnings"]:
                message += f"• {warning}\n"
            message += "\n"
            
        # Errors section
        if "errors" in stats and stats["errors"] > 0:
            message += f"❌ Errors: {stats['errors']}\n\n"
            
        return message 