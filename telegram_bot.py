import os
import asyncio
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv
import logging
import requests
import tempfile
import uuid
from typing import Dict, Any, Optional, List, Union, Tuple
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
        
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN not set in environment variables")
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
            
        if not self.channel_id:
            logger.error("TELEGRAM_CHANNEL_ID not set in environment variables")
            raise ValueError("TELEGRAM_CHANNEL_ID not set")
        
        self.bot = Bot(token=self.token)
        logger.info(f"Telegram bot initialized with channel ID: {self.channel_id}")
        
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
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=f"📝 No new posts found at {now}.\nWill check again on the next run."
            )
            logger.info("'No new posts' notification sent successfully")
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
            
    async def send_status_report(self, stats: Dict[str, Any]) -> bool:
        """Send a status report to the Telegram channel.
        
        Args:
            stats: Dictionary containing statistics to report
            
        Returns:
            bool: True if report was sent successfully, False otherwise
        """
        try:
            logger.info("Sending status report")
            message = f"📊 <b>Shorpy Scraper Status Report</b>\n\n"
            
            if 'posts_processed' in stats:
                message += f"Posts processed: {stats['posts_processed']}\n"
            if 'posts_sent' in stats:
                message += f"Posts sent to Telegram: {stats['posts_sent']}\n"
            if 'errors' in stats:
                message += f"Errors encountered: {stats['errors']}\n"
            if 'last_run' in stats:
                message += f"Last run: {stats['last_run']}\n"
                
            message += f"\nReport time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info("Status report sent successfully")
            return True
        except Exception as e:
            logger.error(f"Error sending status report: {str(e)}")
            return False 