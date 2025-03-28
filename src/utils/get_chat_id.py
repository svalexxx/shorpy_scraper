import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

# Get bot token from .env file
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

def get_updates():
    """Get recent updates (messages) received by the bot."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    response = requests.get(url)
    
    if response.status_code == 200:
        updates = response.json()
        print("Bot Updates:")
        print(json.dumps(updates, indent=2))
        
        # Extract chat IDs from updates
        if updates.get('ok') and updates.get('result'):
            for update in updates['result']:
                message = update.get('message')
                if message and message.get('chat'):
                    chat = message['chat']
                    chat_id = chat.get('id')
                    chat_type = chat.get('type')
                    chat_title = chat.get('title', 'N/A')
                    chat_username = chat.get('username', 'N/A')
                    
                    print(f"\nFound chat:")
                    print(f"  ID: {chat_id}")
                    print(f"  Type: {chat_type}")
                    if chat_type == 'private':
                        print(f"  Username: {chat_username}")
                    else:
                        print(f"  Title: {chat_title}")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    print(f"Getting updates for bot token: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:]}")
    get_updates() 