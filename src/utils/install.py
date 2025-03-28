#!/usr/bin/env python3
"""
Installation script for the Shorpy Scraper project.
This script helps users set up the project by:
1. Creating necessary directories
2. Setting up the .env file
3. Creating the database
4. Installing dependencies
5. Setting up a systemd service (optional)
"""

import os
import sys
import subprocess
import shutil
import getpass
from pathlib import Path
import logging
import argparse
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("shorpy-installer")

# Project root is the parent directory of this script
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

def run_command(command, cwd=None):
    """Run a shell command and return the output."""
    logger.debug(f"Running command: {command}")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            cwd=cwd or PROJECT_ROOT
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            logger.error(f"Command failed: {stderr.decode()}")
            return False, stderr.decode()
        return True, stdout.decode()
    except Exception as e:
        logger.error(f"Failed to run command: {str(e)}")
        return False, str(e)

def create_directories():
    """Create necessary directories for the project."""
    logger.info("Creating necessary directories...")
    
    dirs = [
        "data/scraped_posts",
        "data/temp_images",
        "logs"
    ]
    
    for directory in dirs:
        path = PROJECT_ROOT / directory
        if not path.exists():
            logger.info(f"Creating directory: {path}")
            path.mkdir(parents=True, exist_ok=True)
            # Create .gitkeep file
            (path / ".gitkeep").touch()
    
    logger.info("Directories created successfully.")
    return True

def setup_env_file():
    """Set up the .env file with user input."""
    logger.info("Setting up .env file...")
    
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        logger.info(".env file already exists. Do you want to overwrite it? (y/n)")
        choice = input().lower()
        if choice != 'y':
            logger.info("Skipping .env file setup.")
            return True
    
    print("\n--- Telegram Bot Configuration ---")
    print("Please enter your Telegram bot token (from @BotFather):")
    bot_token = input().strip()
    
    print("\nPlease enter your Telegram channel ID (use @username or -100xxxxxxxxx format):")
    channel_id = input().strip()
    
    print("\nPlease enter your Telegram report channel ID (leave empty to use the same as channel ID):")
    report_channel_id = input().strip() or channel_id
    
    # Write the .env file
    with open(env_path, 'w') as f:
        f.write("# Telegram Bot Token from @BotFather\n")
        f.write(f"TELEGRAM_BOT_TOKEN={bot_token}\n\n")
        f.write("# Telegram Channel ID\n")
        f.write(f"TELEGRAM_CHANNEL_ID={channel_id}\n\n")
        f.write("# Telegram Report Channel ID (for status reports)\n")
        f.write(f"TELEGRAM_REPORT_CHANNEL_ID={report_channel_id}\n")
    
    logger.info(".env file created successfully.")
    return True

def create_database():
    """Create the SQLite database."""
    logger.info("Creating database...")
    
    db_path = PROJECT_ROOT / "shorpy_data.db"
    if db_path.exists():
        logger.info("Database already exists. Do you want to recreate it? (y/n)")
        choice = input().lower()
        if choice != 'y':
            logger.info("Skipping database creation.")
            return True
    
    success, output = run_command("python -m src.database.create_empty_db")
    if success:
        logger.info("Database created successfully.")
        return True
    else:
        logger.error(f"Failed to create database: {output}")
        return False

def install_dependencies():
    """Install dependencies using pip."""
    logger.info("Installing dependencies...")
    
    # Check if virtual environment is active
    if not os.environ.get('VIRTUAL_ENV'):
        logger.warning("Virtual environment not detected. It's recommended to use a virtual environment.")
        logger.info("Do you want to create a virtual environment? (y/n)")
        choice = input().lower()
        if choice == 'y':
            venv_path = PROJECT_ROOT / "venv"
            
            # Create virtual environment
            logger.info("Creating virtual environment...")
            success, output = run_command(f"python -m venv {venv_path}")
            if not success:
                logger.error(f"Failed to create virtual environment: {output}")
                return False
            
            # Activate virtual environment
            if sys.platform == 'win32':
                activate_script = venv_path / "Scripts" / "activate.bat"
                # On Windows, we need to use a different approach to activate the venv
                logger.info(f"Virtual environment created. Please activate it manually with: {activate_script}")
                logger.info("Then run this script again.")
                return False
            else:
                activate_script = venv_path / "bin" / "activate"
                logger.info(f"Virtual environment created. Activating...")
                # Source the activation script and then continue with pip install
                os.environ['VIRTUAL_ENV'] = str(venv_path)
                os.environ['PATH'] = f"{venv_path}/bin:{os.environ['PATH']}"
    
    # Install dependencies
    success, output = run_command("pip install -r requirements.txt")
    if success:
        logger.info("Dependencies installed successfully.")
        return True
    else:
        logger.error(f"Failed to install dependencies: {output}")
        return False

def setup_systemd_service():
    """Set up a systemd service for running the script (Linux only)."""
    if sys.platform != 'linux':
        logger.info("Systemd service setup is only available on Linux.")
        return True
    
    logger.info("Do you want to set up a systemd service to run the scraper automatically? (y/n)")
    choice = input().lower()
    if choice != 'y':
        logger.info("Skipping systemd service setup.")
        return True
    
    # Get username
    username = getpass.getuser()
    
    # Create service file
    service_content = f"""[Unit]
Description=Shorpy Scraper Service
After=network.target

[Service]
Type=simple
User={username}
WorkingDirectory={PROJECT_ROOT}
ExecStart={sys.executable} {PROJECT_ROOT}/main.py --schedule --silent
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
"""
    
    service_path = PROJECT_ROOT / "shorpy-scraper.service"
    with open(service_path, 'w') as f:
        f.write(service_content)
    
    logger.info(f"Service file created at {service_path}")
    logger.info("To install the service, run the following commands as root:")
    logger.info(f"sudo cp {service_path} /etc/systemd/system/")
    logger.info("sudo systemctl daemon-reload")
    logger.info("sudo systemctl enable shorpy-scraper.service")
    logger.info("sudo systemctl start shorpy-scraper.service")
    
    return True

def create_cron_job():
    """Set up a cron job for running the script (Unix/Linux only)."""
    if sys.platform == 'win32':
        logger.info("Cron job setup is not available on Windows.")
        return True
    
    logger.info("Do you want to set up a cron job to run the scraper automatically? (y/n)")
    choice = input().lower()
    if choice != 'y':
        logger.info("Skipping cron job setup.")
        return True
    
    # Create cron entry
    cron_entry = f"0 */6 * * * cd {PROJECT_ROOT} && {sys.executable} {PROJECT_ROOT}/main.py --run-once --silent\n"
    
    # Add to crontab
    cron_path = "/tmp/shorpy-crontab"
    success, output = run_command("crontab -l > /tmp/shorpy-crontab 2>/dev/null || true")
    
    with open(cron_path, 'a') as f:
        f.write(cron_entry)
    
    success, output = run_command("crontab /tmp/shorpy-crontab")
    os.remove(cron_path)
    
    if success:
        logger.info("Cron job set up successfully.")
        return True
    else:
        logger.error(f"Failed to set up cron job: {output}")
        return False

def make_script_executable():
    """Make the shorpy.sh script executable."""
    logger.info("Making shell script executable...")
    
    script_path = PROJECT_ROOT / "scripts" / "shorpy.sh"
    if script_path.exists():
        success, output = run_command(f"chmod +x {script_path}")
        if success:
            logger.info("Shell script is now executable.")
            return True
        else:
            logger.error(f"Failed to make shell script executable: {output}")
            return False
    else:
        logger.warning("Shell script not found at expected path.")
        return False

def test_setup():
    """Test the setup by running the validation script."""
    logger.info("Testing setup...")
    
    success, output = run_command("python -m src.utils.validate_setup")
    if success:
        logger.info("Setup validation successful.")
        return True
    else:
        logger.error(f"Setup validation failed: {output}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Install Shorpy Scraper")
    parser.add_argument("--no-venv", action="store_true", help="Skip virtual environment creation")
    parser.add_argument("--no-deps", action="store_true", help="Skip dependency installation")
    parser.add_argument("--no-systemd", action="store_true", help="Skip systemd service setup")
    parser.add_argument("--no-cron", action="store_true", help="Skip cron job setup")
    parser.add_argument("--no-test", action="store_true", help="Skip setup testing")
    
    args = parser.parse_args()
    
    logger.info("Starting Shorpy Scraper installation...")
    
    # Steps
    steps = [
        ("Creating directories", create_directories),
        ("Setting up .env file", setup_env_file),
        ("Creating database", create_database),
    ]
    
    if not args.no_deps:
        steps.append(("Installing dependencies", install_dependencies))
    
    steps.append(("Making shell script executable", make_script_executable))
    
    if not args.no_systemd and sys.platform == 'linux':
        steps.append(("Setting up systemd service", setup_systemd_service))
    
    if not args.no_cron and sys.platform != 'win32':
        steps.append(("Setting up cron job", create_cron_job))
    
    if not args.no_test:
        steps.append(("Testing setup", test_setup))
    
    # Run steps
    for step_name, step_func in steps:
        logger.info(f"\n--- {step_name} ---")
        if not step_func():
            logger.error(f"Failed at step: {step_name}")
            logger.info("Installation incomplete. Please fix the errors and try again.")
            return 1
    
    logger.info("\n--- Installation Complete ---")
    logger.info("Shorpy Scraper has been successfully installed!")
    logger.info("\nTo run the scraper:")
    logger.info("  - Single run: python main.py --run-once")
    logger.info("  - Schedule mode: python main.py --schedule")
    logger.info("  - Using shell script: ./scripts/shorpy.sh run")
    logger.info("\nEnjoy your Shorpy photos!")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 