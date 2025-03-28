#!/usr/bin/env python3
"""
Validation script to check that the Shorpy Scraper setup is correct.
Performs checks on the environment, directories, dependencies, and configuration.
"""

import os
import sys
import socket
import time
import logging
import platform
import importlib
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("shorpy-validator")

# Project root is the parent directory of this script
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

def check_python_version():
    """Check that Python version is 3.7 or higher."""
    logger.info("Checking Python version...")
    version = platform.python_version_tuple()
    if int(version[0]) >= 3 and int(version[1]) >= 7:
        logger.info(f"✅ Python version is {platform.python_version()} (3.7+ required)")
        return True
    else:
        logger.error(f"❌ Python version is {platform.python_version()} (3.7+ required)")
        return False

def check_directories():
    """Check that required directories exist."""
    logger.info("Checking required directories...")
    
    required_dirs = [
        "data/scraped_posts",
        "data/temp_images",
        "logs",
        "src/scraper",
        "src/bot",
        "src/database",
        "src/utils",
        "scripts"
    ]
    
    all_exist = True
    for directory in required_dirs:
        path = PROJECT_ROOT / directory
        if path.exists() and path.is_dir():
            logger.info(f"✅ Directory exists: {directory}")
        else:
            logger.error(f"❌ Directory missing: {directory}")
            all_exist = False
    
    return all_exist

def check_required_files():
    """Check that required files exist."""
    logger.info("Checking required files...")
    
    required_files = [
        "main.py",
        "requirements.txt",
        "src/scraper/shorpy.py",
        "src/bot/telegram_bot.py",
        "src/database/models.py",
        "scripts/shorpy.sh"
    ]
    
    all_exist = True
    for file in required_files:
        path = PROJECT_ROOT / file
        if path.exists() and path.is_file():
            logger.info(f"✅ File exists: {file}")
        else:
            logger.error(f"❌ File missing: {file}")
            all_exist = False
    
    return all_exist

def check_dependencies():
    """Check that required Python dependencies are installed."""
    logger.info("Checking Python dependencies...")
    
    required_packages = [
        "requests",
        "beautifulsoup4",
        "python-telegram-bot",
        "schedule",
        "python-dotenv",
        "aiohttp",
        "aiofiles",
        "tenacity"
    ]
    
    all_installed = True
    for package in required_packages:
        try:
            importlib.import_module(package.replace('-', '_'))
            logger.info(f"✅ Package installed: {package}")
        except ImportError:
            logger.error(f"❌ Package missing: {package}")
            all_installed = False
    
    return all_installed

def check_env_file():
    """Check that .env file exists and has required variables."""
    logger.info("Checking .env file...")
    
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        logger.error("❌ .env file not found")
        return False
    
    # Load environment variables
    load_dotenv(env_path)
    
    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID"
    ]
    
    all_vars_set = True
    for var in required_vars:
        if os.getenv(var):
            logger.info(f"✅ Environment variable set: {var}")
        else:
            logger.error(f"❌ Environment variable missing: {var}")
            all_vars_set = False
    
    return all_vars_set

def check_database():
    """Check that database exists and has required tables."""
    logger.info("Checking database...")
    
    db_path = PROJECT_ROOT / "shorpy_data.db"
    if not db_path.exists():
        logger.error("❌ Database file not found")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ["parsed_posts", "urls"]
        all_tables_exist = True
        
        for table in required_tables:
            if table in tables:
                logger.info(f"✅ Database table exists: {table}")
            else:
                logger.error(f"❌ Database table missing: {table}")
                all_tables_exist = False
        
        conn.close()
        return all_tables_exist
    
    except sqlite3.Error as e:
        logger.error(f"❌ Database error: {str(e)}")
        return False

def check_network():
    """Check network connectivity to shorpy.com and Telegram API."""
    logger.info("Checking network connectivity...")
    
    targets = [
        ("shorpy.com", 443),
        ("api.telegram.org", 443)
    ]
    
    all_reachable = True
    for host, port in targets:
        try:
            # Create socket connection to check if service is reachable
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                logger.info(f"✅ Network connection successful: {host}:{port}")
            else:
                logger.error(f"❌ Network connection failed: {host}:{port}")
                all_reachable = False
        
        except Exception as e:
            logger.error(f"❌ Network error for {host}:{port} - {str(e)}")
            all_reachable = False
    
    return all_reachable

def check_permissions():
    """Check that script has necessary permissions."""
    logger.info("Checking permissions...")
    
    # Check data directory is writable
    data_dir = PROJECT_ROOT / "data"
    db_file = PROJECT_ROOT / "shorpy_data.db"
    
    all_permissions_ok = True
    try:
        test_file = data_dir / "permission_test.txt"
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        logger.info("✅ Data directory is writable")
    except Exception as e:
        logger.error(f"❌ Data directory is not writable: {str(e)}")
        all_permissions_ok = False
    
    # Check database is writable
    try:
        if db_file.exists():
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Try to write to a temporary table
            cursor.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY)")
            cursor.execute("DROP TABLE IF EXISTS test_table")
            
            conn.close()
            logger.info("✅ Database is writable")
        else:
            logger.warning("⚠️ Database doesn't exist, skipping write test")
    except Exception as e:
        logger.error(f"❌ Database is not writable: {str(e)}")
        all_permissions_ok = False
    
    return all_permissions_ok

def main():
    """Run all validation checks."""
    logger.info("Starting Shorpy Scraper validation...\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("Required Directories", check_directories),
        ("Required Files", check_required_files),
        ("Dependencies", check_dependencies),
        ("Environment Variables", check_env_file),
        ("Database", check_database),
        ("Network Connectivity", check_network),
        ("Permissions", check_permissions)
    ]
    
    results = {}
    
    for check_name, check_func in checks:
        logger.info(f"\n--- {check_name} Check ---")
        try:
            result = check_func()
            results[check_name] = result
        except Exception as e:
            logger.error(f"❌ Check failed with error: {str(e)}")
            results[check_name] = False
    
    # Summary
    logger.info("\n--- Validation Summary ---")
    all_checks_passed = True
    
    for check_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {check_name}")
        if not result:
            all_checks_passed = False
    
    if all_checks_passed:
        logger.info("\n✅ All checks passed! Your Shorpy Scraper setup is valid.")
        return 0
    else:
        logger.error("\n❌ Some checks failed. Please fix the issues and run validation again.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 