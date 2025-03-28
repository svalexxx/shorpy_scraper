import os
import asyncio
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv
import logging
import requests
import tempfile
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Use the same temp directory as main.py
TEMP_DIR = "temp_images"
os.makedirs(TEMP_DIR, exist_ok=True)

class TelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
        # Remove @ symbol if present and convert to string
        self.channel_id = str(self.channel_id).lstrip('@')
        logger.info(f"Bot initialized with token: {self.bot_token[:5]}...{self.bot_token[-5:]}")
        logger.info(f"Channel ID: {self.channel_id}")
        print(f"Bot initialized with token: {self.bot_token[:5]}...{self.bot_token[-5:]}")
        print(f"Channel ID: {self.channel_id}")
        
        try:
            self.bot = Bot(token=self.bot_token)
            logger.info("Bot created successfully")
            print("Bot created successfully")
        except Exception as e:
            logger.error(f"Error creating bot: {str(e)}")
            print(f"Error creating bot: {str(e)}")
            raise
    
    async def test_connection(self, silent=False):
        """Test if the bot can connect to Telegram API and send a message."""
        try:
            logger.info("Testing connection to Telegram API...")
            print("Testing connection to Telegram API...")
            
            # First test if we can get bot info
            try:
                bot_info = await self.bot.get_me()
                logger.info(f"Connected as: {bot_info.username}")
                print(f"Connected as: {bot_info.username}")
            except Exception as e:
                logger.error(f"Could not get bot info: {str(e)}")
                print(f"Could not get bot info: {str(e)}")
                return False
            
            # If silent mode is enabled, skip sending the test message
            if silent:
                logger.info("Silent mode enabled, skipping test message")
                print("Silent mode enabled, skipping test message")
                return True
            
            # Now try to post a simple test message
            logger.info(f"Testing sending message to channel: {self.channel_id}")
            print(f"Testing sending message to channel: {self.channel_id}")
            
            try:
                message = await self.bot.send_message(
                    chat_id=self.channel_id,
                    text="Test message from Shorpy Telegram Bot. If you see this message, the bot is working correctly!"
                )
                logger.info(f"Test message sent successfully! Message ID: {message.message_id}")
                print(f"Test message sent successfully! Message ID: {message.message_id}")
                return True
            except TelegramError as e:
                logger.error(f"Could not send test message: {str(e)}")
                print(f"Could not send test message: {str(e)}")
                
                # Check for common errors
                error_text = str(e).lower()
                if "chat not found" in error_text:
                    logger.error("The channel ID may be incorrect or the bot is not a member of the channel")
                    print("The channel ID may be incorrect or the bot is not a member of the channel")
                elif "bot was blocked by the user" in error_text:
                    logger.error("The bot was blocked by the user")
                    print("The bot was blocked by the user")
                elif "not enough rights" in error_text:
                    logger.error("The bot doesn't have enough permissions in the channel")
                    print("The bot doesn't have enough permissions in the channel")
                
                return False
            
        except Exception as e:
            logger.error(f"Unexpected error during connection test: {str(e)}")
            print(f"Unexpected error during connection test: {str(e)}")
            return False
    
    async def send_post(self, post_data):
        try:
            # Prepare message text
            message_text = f"📸 {post_data['title']}\n\n"
            if post_data['description']:
                message_text += f"{post_data['description']}\n\n"
            message_text += f"🔗 {post_data['post_url']}"
            
            logger.info(f"Trying to send message to {self.channel_id}")
            print(f"Trying to send message to {self.channel_id}")
            
            # Send image if available
            if post_data['image_url']:
                logger.info(f"Processing image: {post_data['image_url']}")
                print(f"Processing image: {post_data['image_url']}")
                
                # Try to download the image
                try:
                    # Generate a unique filename
                    file_extension = os.path.splitext(post_data['image_url'])[1] or '.jpg'
                    temp_file = os.path.join(TEMP_DIR, f"{uuid.uuid4()}{file_extension}")
                    
                    # Download the image
                    print(f"Downloading image to {temp_file}")
                    response = requests.get(post_data['image_url'], stream=True)
                    response.raise_for_status()
                    
                    with open(temp_file, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print(f"Image downloaded successfully: {temp_file}")
                    
                    # Send as photo
                    try:
                        print(f"Sending image from local file: {temp_file}")
                        with open(temp_file, 'rb') as photo:
                            await self.bot.send_photo(
                                chat_id=self.channel_id,
                                photo=photo,
                                caption=message_text,
                                parse_mode='HTML'
                            )
                        print("Image sent successfully from local file")
                        
                        # Clean up the temp file
                        try:
                            os.remove(temp_file)
                            print(f"Removed temporary file: {temp_file}")
                        except Exception as cleanup_error:
                            print(f"Error removing temp file: {str(cleanup_error)}")
                        
                        logger.info("Message sent successfully")
                        print("Message sent successfully")
                        return True
                    except Exception as send_error:
                        print(f"Error sending local image: {str(send_error)}")
                        # Continue to fallback methods
                except Exception as download_error:
                    print(f"Error downloading image: {str(download_error)}")
                    # Continue to fallback methods
                
                # If local file approach failed, try the URL methods
                try:
                    # First try sending as photo directly from URL
                    await self.bot.send_photo(
                        chat_id=self.channel_id,
                        photo=post_data['image_url'],
                        caption=message_text,
                        parse_mode='HTML'
                    )
                except Exception as img_error:
                    logger.error(f"Error sending as photo: {str(img_error)}")
                    print(f"Error sending as photo: {str(img_error)}")
                    
                    try:
                        # Try sending as URL with web page preview enabled
                        await self.bot.send_message(
                            chat_id=self.channel_id,
                            text=f"{message_text}\n\n{post_data['image_url']}",
                            parse_mode='HTML',
                            disable_web_page_preview=False
                        )
                    except Exception as url_error:
                        logger.error(f"Error sending with URL: {str(url_error)}")
                        print(f"Error sending with URL: {str(url_error)}")
                        logger.info("Falling back to text-only message")
                        print("Falling back to text-only message")
                        await self.bot.send_message(
                            chat_id=self.channel_id,
                            text=f"{message_text}\n\nImage URL: {post_data['image_url']}",
                            parse_mode='HTML'
                        )
            else:
                logger.info("Sending text-only message")
                print("Sending text-only message")
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=message_text,
                    parse_mode='HTML'
                )
            
            logger.info("Message sent successfully")
            print("Message sent successfully")
            return True
            
        except TelegramError as e:
            logger.error(f"Error sending message to Telegram: {str(e)}")
            print(f"Error sending message to Telegram: {str(e)}")
            if "chat not found" in str(e).lower():
                logger.error("The channel ID may be incorrect or the bot is not a member of the channel")
                logger.error("Make sure the bot is added as an administrator to the channel")
                logger.error(f"Current channel ID: {self.channel_id}")
                print("The channel ID may be incorrect or the bot is not a member of the channel")
                print("Make sure the bot is added as an administrator to the channel")
                print(f"Current channel ID: {self.channel_id}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending message: {str(e)}")
            print(f"Unexpected error sending message: {str(e)}")
            return False 

    async def send_no_posts_message(self):
        """Send a message indicating that no new posts were found."""
        try:
            message_text = "📢 No new posts found at Shorpy.com during the latest check."
            
            logger.info(f"Sending 'no new posts' message to channel: {self.channel_id}")
            print(f"Sending 'no new posts' message to channel: {self.channel_id}")
            
            message = await self.bot.send_message(
                chat_id=self.channel_id,
                text=message_text
            )
            
            logger.info(f"'No posts' message sent successfully! Message ID: {message.message_id}")
            print(f"'No posts' message sent successfully! Message ID: {message.message_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending 'no posts' message: {str(e)}")
            print(f"Error sending 'no posts' message: {str(e)}")
            return False 