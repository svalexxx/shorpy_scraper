#!/usr/bin/env python3
"""
Configuration system for the Shorpy Scraper application.
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logger
logger = logging.getLogger(__name__)

class Config:
    """Centralized configuration management for the application."""
    
    def __init__(self):
        """Initialize configuration with default values and overrides."""
        self.config_dir = os.path.join(os.getcwd(), "config")
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Default configuration values
        self.defaults = {
            # Application settings
            "app_name": "shorpy_scraper",
            "log_level": "INFO",
            "timezone": "UTC",
            
            # Directories
            "output_dir": "scraped_posts",
            "temp_dir": "temp_images",
            "metrics_dir": "metrics",
            
            # Scraper settings
            "shorpy_base_url": "https://www.shorpy.com",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "request_timeout": 30,
            "max_retries": 3,
            "retry_delay": 1.0,
            "max_posts_per_run": 5,
            
            # Database settings
            "db_path": "shorpy_data.db",
            "db_timeout": 20.0,
            
            # Telegram settings
            "telegram_api_url": "https://api.telegram.org",
            "telegram_send_mode": "html",
            "telegram_disable_web_page_preview": False,
            "telegram_disable_notification": False,
            
            # Webhook settings
            "webhook_port": 8080,
            "webhook_host": "0.0.0.0",
            
            # Schedule settings
            "schedule_interval_minutes": 60,
            "check_new_posts_interval_hours": 1,
        }
        
        # Environment variable configuration
        self.env_vars = {
            # Critical settings that must be provided via environment variables
            "TELEGRAM_BOT_TOKEN": None,
            "TELEGRAM_CHANNEL_ID": None,
            "TELEGRAM_REPORT_CHANNEL_ID": None,
            "GITHUB_TOKEN": None,
            "GITHUB_REPO_OWNER": None,
            "GITHUB_REPO_NAME": None,
            
            # Optional settings with defaults
            "LOG_LEVEL": self.defaults["log_level"],
            "OUTPUT_DIR": self.defaults["output_dir"],
            "TEMP_DIR": self.defaults["temp_dir"],
            "DB_PATH": self.defaults["db_path"],
            "REQUEST_TIMEOUT": str(self.defaults["request_timeout"]),
            "MAX_RETRIES": str(self.defaults["max_retries"]),
            "SCHEDULE_INTERVAL_MINUTES": str(self.defaults["schedule_interval_minutes"]),
        }
        
        # Load configuration from files
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.file_config = self._load_file_config()
        
        # Merge configurations with priority: env vars > config file > defaults
        self.current = self._merge_configs()
        
        # Validate critical settings
        self._validate_config()
    
    def _load_file_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading config file {self.config_file}: {str(e)}")
        return {}
    
    def _merge_configs(self) -> Dict[str, Any]:
        """Merge configuration sources with priority."""
        # Start with defaults
        merged = self.defaults.copy()
        
        # Override with file config
        merged.update(self.file_config)
        
        # Override with environment variables
        for key, default in self.env_vars.items():
            env_value = os.getenv(key, default)
            if env_value is not None:
                # Convert environment variables to appropriate types
                try:
                    if isinstance(self.defaults.get(key.lower(), ""), (int, float)):
                        if isinstance(self.defaults.get(key.lower(), ""), int):
                            merged[key.lower()] = int(env_value)
                        else:
                            merged[key.lower()] = float(env_value)
                    elif isinstance(self.defaults.get(key.lower(), ""), bool):
                        merged[key.lower()] = env_value.lower() in ('true', 'yes', 'y', '1')
                    else:
                        merged[key.lower()] = env_value
                except (ValueError, TypeError):
                    # If conversion fails, use the string value
                    merged[key.lower()] = env_value
        
        return merged
    
    def _validate_config(self) -> None:
        """Validate that critical configuration values are present."""
        critical_keys = ["telegram_bot_token", "telegram_channel_id"]
        missing = [key for key in critical_keys if not self.get(key)]
        
        if missing:
            logger.warning(f"Missing critical configuration values: {', '.join(missing)}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self.current.get(key.lower(), default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        self.current[key.lower()] = value
        
        # Update file configuration
        self.file_config[key.lower()] = value
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.file_config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving config to {self.config_file}: {str(e)}")
    
    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration values.
        
        Returns:
            Dictionary with all configuration values
        """
        return self.current.copy()
    
    def load_custom_config(self, filepath: str) -> bool:
        """
        Load configuration from a custom file.
        
        Args:
            filepath: Path to configuration file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'r') as f:
                custom_config = json.load(f)
            
            # Update current configuration
            self.current.update(custom_config)
            
            # Save to default config file
            with open(self.config_file, 'w') as f:
                json.dump(self.file_config, f, indent=2)
                
            return True
        except Exception as e:
            logger.error(f"Error loading custom config from {filepath}: {str(e)}")
            return False

# Create a singleton instance
config = Config() 