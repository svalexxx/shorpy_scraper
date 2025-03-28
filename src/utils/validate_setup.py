#!/usr/bin/env python
"""
Validation script to check environment configuration and dependencies
before deploying to GitHub Actions.
"""
import os
import sys
import sqlite3
import requests
from dotenv import load_dotenv

def check_environment():
    """Check if all required environment variables are set."""
    print("Checking environment variables...")
    
    # Load .env file
    load_dotenv()
    
    # Check Telegram Bot Token
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN is not set")
        return False
    print("✅ TELEGRAM_BOT_TOKEN is set")
    
    # Check Telegram Channel ID
    channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not channel_id:
        print("❌ TELEGRAM_CHANNEL_ID is not set")
        return False
    print("✅ TELEGRAM_CHANNEL_ID is set")
    
    return True

def test_telegram_api():
    """Test connection to Telegram API."""
    print("Testing Telegram API connection...")
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
    
    # Test getMe endpoint
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe")
        response.raise_for_status()
        data = response.json()
        
        if data.get('ok'):
            print(f"✅ Bot connection successful: @{data['result']['username']}")
        else:
            print(f"❌ Bot connection failed: {data.get('description', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"❌ Error connecting to Telegram API: {str(e)}")
        return False
    
    # Test channel/chat access
    try:
        # Format channel_id - remove @ if present
        if channel_id.startswith('@'):
            chat_id = channel_id
        else:
            chat_id = channel_id
            
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "🧪 Test message from validation script. If you see this, setup is correct!"
            }
        )
        
        data = response.json()
        if data.get('ok'):
            print(f"✅ Message sent to channel successfully")
        else:
            print(f"❌ Message to channel failed: {data.get('description', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"❌ Error sending message to channel: {str(e)}")
        return False
    
    return True

def check_db_access():
    """Test database access and schema."""
    print("Testing database access...")
    
    # Check if DB file exists, create it if not
    db_path = "shorpy_data.db"
    db_exists = os.path.exists(db_path)
    
    if db_exists:
        print(f"✅ Database file exists: {db_path}")
    else:
        print(f"ℹ️ Database file does not exist, will be created: {db_path}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['parsed_posts', 'checkpoints']
        missing_tables = [table for table in expected_tables if table not in tables]
        
        if missing_tables:
            print(f"ℹ️ Some tables are missing: {', '.join(missing_tables)}")
            print("   These will be created when the script runs.")
        else:
            print("✅ All required tables exist")
            
            # Check 'published' column in parsed_posts table
            cursor.execute("PRAGMA table_info(parsed_posts)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'published' in columns:
                print("✅ 'published' column exists in parsed_posts table")
            else:
                print("ℹ️ 'published' column is missing, will be created when the script runs")
        
    except Exception as e:
        print(f"❌ Error checking database: {str(e)}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
    
    return True

def check_directories():
    """Check required directories exist."""
    print("Checking required directories...")
    
    required_dirs = ['scraped_posts', 'temp_images']
    for directory in required_dirs:
        if os.path.exists(directory) and os.path.isdir(directory):
            print(f"✅ Directory exists: {directory}")
        else:
            print(f"ℹ️ Directory does not exist, will be created: {directory}")
    
    return True

def main():
    """Run all checks."""
    print("=" * 50)
    print("Shorpy Scraper Setup Validation")
    print("=" * 50)
    
    # Run all checks
    env_check = check_environment()
    dir_check = check_directories()
    db_check = check_db_access()
    
    # Only test Telegram if environment variables are set
    telegram_check = False
    if env_check:
        telegram_check = test_telegram_api()
    
    # Print summary
    print("\n" + "=" * 50)
    print("Validation Summary:")
    print(f"Environment: {'✅ PASS' if env_check else '❌ FAIL'}")
    print(f"Directories: {'✅ PASS' if dir_check else '❌ FAIL'}")
    print(f"Database: {'✅ PASS' if db_check else '❌ FAIL'}")
    print(f"Telegram API: {'✅ PASS' if telegram_check else '❌ FAIL' if env_check else '⏭️ SKIPPED'}")
    
    # Final result
    all_passed = env_check and dir_check and db_check and (telegram_check if env_check else True)
    print("\nFinal Result:", "✅ READY FOR GITHUB ACTIONS" if all_passed else "❌ ISSUES FOUND")
    print("=" * 50)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main()) 