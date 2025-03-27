import requests
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Get bot token from .env file
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

def send_test_message(chat_id):
    """Send a test message to the specified chat ID."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': "Test message from Shorpy Telegram Bot. If you see this message, the bot is working correctly!"
    }
    
    print(f"Sending test message to chat_id: {chat_id}")
    response = requests.post(url, data=payload)
    
    print(f"Response status code: {response.status_code}")
    print(f"Response text: {response.text}")
    
    if response.status_code == 200:
        print("Message sent successfully!")
        return True
    else:
        print("Failed to send message.")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        chat_id = sys.argv[1]
    else:
        chat_id = input("Enter the chat ID to send a test message to: ")
    
    print(f"Using bot token: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:]}")
    send_test_message(chat_id) 