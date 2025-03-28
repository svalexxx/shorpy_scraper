import asyncio
import os
import sys
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
import requests
import tempfile
import uuid
from models import storage

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

async def get_bot_info():
    """Get information about the bot."""
    try:
        bot = Bot(token=BOT_TOKEN)
        me = await bot.get_me()
        print(f"Bot information:")
        print(f"  ID: {me.id}")
        print(f"  Name: {me.first_name}")
        print(f"  Username: @{me.username}")
        return True
    except Exception as e:
        print(f"Error getting bot info: {str(e)}")
        return False

async def get_chat_info(chat_id):
    """Get information about the channel."""
    try:
        bot = Bot(token=BOT_TOKEN)
        chat = await bot.get_chat(chat_id)
        print(f"Chat information:")
        print(f"  ID: {chat.id}")
        print(f"  Type: {chat.type}")
        if chat.type == 'channel':
            print(f"  Title: {chat.title}")
            print(f"  Username: @{chat.username}" if chat.username else "  Username: None (private channel)")
        return True
    except Exception as e:
        print(f"Error getting chat info: {str(e)}")
        print(f"If 'chat not found', it means the bot doesn't have access to the channel.")
        print(f"1. Make sure the channel exists")
        print(f"2. Make sure the bot is added as an administrator to the channel")
        print(f"3. Make sure the channel ID is correct")
        return False

async def send_test_message(chat_id):
    """Send a test message to the channel."""
    try:
        bot = Bot(token=BOT_TOKEN)
        message = await bot.send_message(
            chat_id=chat_id,
            text="🔍 Test message from Shorpy Telegram Bot\n\nIf you see this message, the bot is working correctly!"
        )
        print(f"Message sent successfully to {chat_id}!")
        print(f"Message ID: {message.message_id}")
        return True
    except TelegramError as e:
        print(f"Error sending message: {str(e)}")
        
        # Check for specific errors
        error_msg = str(e).lower()
        if "chat not found" in error_msg:
            print("\nERROR: Chat not found. Possible reasons:")
            print("1. The channel doesn't exist")
            print("2. The bot is not a member of the channel")
            print("3. The channel ID format is incorrect")
            print("\nSUGGESTIONS:")
            print("- For public channels: use @channel_username format")
            print("- For private channels: use -100xxxxxxxxxx format")
        elif "not enough rights" in error_msg:
            print("\nERROR: Bot doesn't have enough permissions.")
            print("Make sure the bot is an administrator with 'Post Messages' permission enabled.")
        elif "bot was blocked" in error_msg:
            print("\nERROR: The bot was blocked by the user/channel.")
            
        return False
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return False

async def manual_rest_post(chat_id):
    """Manually post to Telegram using REST API."""
    print("\nTrying direct REST API approach:")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {
        'chat_id': chat_id,
        'text': "Direct API test message from Shorpy Telegram Bot"
    }
    
    try:
        response = requests.post(url, data=params)
        print(f"Response code: {response.status_code}")
        print(f"Response body: {response.text}")
        if response.status_code == 200:
            print("Message sent successfully using direct API!")
            return True
        return False
    except Exception as e:
        print(f"Error with direct API request: {str(e)}")
        return False

async def send_test_image(chat_id):
    """Send a test image to the channel."""
    try:
        bot = Bot(token=BOT_TOKEN)
        
        # Test image URL (using a reliable public image)
        test_image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg/800px-Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg"
        
        print(f"Sending test image from URL: {test_image_url}")
        
        # Try downloading the image first
        try:
            # Create a temporary file for the image
            temp_dir = os.path.join(os.getcwd(), "temp_images")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate a unique filename
            temp_file = os.path.join(temp_dir, f"{uuid.uuid4()}.jpg")
            
            # Download the image
            print(f"Downloading image to {temp_file}")
            response = requests.get(test_image_url, stream=True)
            response.raise_for_status()
            
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Image downloaded successfully: {temp_file}")
            
            # Send as photo
            with open(temp_file, 'rb') as photo:
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption="Test image from Shorpy Telegram Bot"
                )
                
            print(f"Image sent successfully from local file!")
            print(f"Message ID: {message.message_id}")
            
            # Clean up the temp file
            try:
                os.remove(temp_file)
                print(f"Removed temporary file: {temp_file}")
            except Exception as cleanup_error:
                print(f"Error removing temp file: {str(cleanup_error)}")
                
            return True
        except Exception as download_error:
            print(f"Error with local file approach: {str(download_error)}")
            
            # Try sending directly from URL
            print("Trying to send image directly from URL...")
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=test_image_url,
                caption="Test image from Shorpy Telegram Bot"
            )
            print(f"Image sent successfully from URL!")
            print(f"Message ID: {message.message_id}")
            return True
        
    except TelegramError as e:
        print(f"Error sending image: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error sending image: {str(e)}")
        return False

def check_checkpoint_info():
    """Check and display checkpoint information."""
    print("\nCheckpoint Information:")
    last_url = storage.get_checkpoint('last_post_url')
    last_title = storage.get_checkpoint('last_post_title')
    last_time = storage.get_checkpoint('last_processed_time')
    
    if last_url and last_title:
        print(f"Last processed post: {last_title}")
        print(f"URL: {last_url}")
        print(f"Processed at: {last_time or 'Unknown'}")
        print(f"Total posts processed: {storage.get_post_count()}")
    else:
        print("No checkpoint information available yet.")

async def run_tests():
    """Run a series of tests to diagnose Telegram issues."""
    global CHANNEL_ID
    
    print(f"Using bot token: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:]}")
    print(f"Using channel ID: {CHANNEL_ID}")
    
    print("\nStep 1: Check bot information")
    if not await get_bot_info():
        print("❌ Bot information test failed")
        return
    print("✅ Bot information test passed")
    
    print("\nStep 2: Check channel information")
    channel_ok = await get_chat_info(CHANNEL_ID)
    if not channel_ok:
        print("❌ Channel information test failed")
        print("\nTrying without the @ symbol (if applicable):")
        if CHANNEL_ID.startswith('@'):
            channel_without_at = CHANNEL_ID[1:]
            print(f"Testing with: {channel_without_at}")
            if await get_chat_info(channel_without_at):
                print(f"✅ Channel test passed with modified ID! Update your .env file to use: {channel_without_at}")
                CHANNEL_ID = channel_without_at
            else:
                await manual_rest_post(CHANNEL_ID)
                return
    else:
        print("✅ Channel information test passed")
    
    print("\nStep 3: Send test message")
    if await send_test_message(CHANNEL_ID):
        print("✅ Message test passed")
    else:
        print("❌ Message test failed")
        await manual_rest_post(CHANNEL_ID)
    
    print("\nStep 4: Send test image")
    if await send_test_image(CHANNEL_ID):
        print("✅ Image test passed")
    else:
        print("❌ Image test failed")
    
    print("\nStep 5: Check checkpoint information")
    check_checkpoint_info()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Telegram channel connection")
    parser.add_argument("--checkpoint", action="store_true", help="Only check checkpoint information")
    args = parser.parse_args()
    
    if args.checkpoint:
        check_checkpoint_info()
    else:
        asyncio.run(run_tests()) 