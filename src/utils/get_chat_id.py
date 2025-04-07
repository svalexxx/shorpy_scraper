#!/usr/bin/env python
"""
Utility script to get your Telegram chat ID for reports.

1. Start a chat with your bot
2. Send a message to the bot
3. Run this script to get your chat ID
4. Use this chat ID as your TELEGRAM_REPORT_RECIPIENT
"""

import os
import asyncio
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN environment variable is not set.")
    sys.exit(1)

async def get_chat_id():
    """Get the chat ID of users who have messaged the bot."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if not data["ok"]:
            print(f"Error from Telegram API: {data.get('description', 'Unknown error')}")
            return
        
        updates = data.get("result", [])
        
        if not updates:
            print("\n⚠️ No messages found.")
            print("Please make sure to:")
            print("1. Start a conversation with your bot")
            print("2. Send at least one message to your bot")
            print("3. Run this script again\n")
            return
        
        print("\n📱 Chat IDs from recent messages:")
        print("=" * 40)
        
        seen_chats = set()
        
        for update in updates:
            message = update.get("message", {})
            callback_query = update.get("callback_query", {})
            
            if message:
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                first_name = chat.get("first_name", "Unknown")
                last_name = chat.get("last_name", "")
                username = chat.get("username", "No username")
                chat_type = chat.get("type", "Unknown")
                
                if chat_id and chat_id not in seen_chats:
                    seen_chats.add(chat_id)
                    print(f"👤 User: {first_name} {last_name}")
                    print(f"🔑 Chat ID: {chat_id}  (This is what you need for reports)")
                    print(f"👤 Username: @{username}")
                    print(f"📝 Chat type: {chat_type}")
                    print("-" * 40)
            
            elif callback_query:
                message = callback_query.get("message", {})
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                from_user = callback_query.get("from", {})
                first_name = from_user.get("first_name", "Unknown")
                last_name = from_user.get("last_name", "")
                username = from_user.get("username", "No username")
                
                if chat_id and chat_id not in seen_chats:
                    seen_chats.add(chat_id)
                    print(f"👤 User: {first_name} {last_name}")
                    print(f"🔑 Chat ID: {chat_id}  (This is what you need for reports)")
                    print(f"👤 Username: @{username}")
                    print("-" * 40)
        
        if seen_chats:
            print("\n✅ How to use:")
            print("Add this line to your .env file:")
            first_chat_id = next(iter(seen_chats))
            print(f"TELEGRAM_REPORT_RECIPIENT={first_chat_id}")
            print("\nOr use it directly with the command:")
            print(f"python main.py --run-once --report-to {first_chat_id}")
        else:
            print("\n⚠️ No valid chat IDs found.")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(get_chat_id()) 