#!/usr/bin/env python3
"""
Telegram webhook handler to receive button callbacks and trigger GitHub Actions workflows.
This script can be deployed to a server or serverless function to handle Telegram webhook events.

Usage:
1. Deploy this script to a server or serverless function
2. Set up a webhook with Telegram using: https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}
3. Configure the GitHub token and repository details below
"""

import os
import json
import hmac
import hashlib
import logging
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("telegram-webhook")

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # Personal access token with 'workflow' scope
GITHUB_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER')  # e.g., 'username'
GITHUB_REPO_NAME = os.getenv('GITHUB_REPO_NAME')  # e.g., 'shorpy_scraper'
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')  # Secret to validate the webhook

# Initialize Flask app
app = Flask(__name__)

def verify_telegram_request(request_data):
    """Verify that the request came from Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False
    
    # In a production environment, you would verify the request using a more robust method
    # This is a simple check that the request contains a valid Telegram update
    try:
        data = json.loads(request_data)
        if 'update_id' not in data:
            logger.warning("Invalid Telegram update format")
            return False
        return True
    except Exception as e:
        logger.error(f"Error verifying Telegram request: {str(e)}")
        return False

def trigger_github_action(action_type='send_posts'):
    """Trigger a GitHub Actions workflow."""
    if not all([GITHUB_TOKEN, GITHUB_REPO_OWNER, GITHUB_REPO_NAME]):
        logger.error("GitHub configuration incomplete")
        return False
    
    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/actions/workflows/last10posts.yml/dispatches"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "ref": "master",  # or "main", depending on your default branch
        "inputs": {
            "type": action_type
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 204:
            logger.info(f"Successfully triggered GitHub Action: {action_type}")
            return True
        else:
            logger.error(f"Error triggering GitHub Action: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception when triggering GitHub Action: {str(e)}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook events from Telegram."""
    if not verify_telegram_request(request.data):
        return jsonify({"status": "error", "message": "Invalid request"}), 403
    
    try:
        data = json.loads(request.data)
        
        # Handle callback queries (button clicks)
        if 'callback_query' in data:
            callback_data = data['callback_query']['data']
            
            if callback_data == 'show_last_10_posts':
                # Trigger GitHub Actions workflow to send last 10 posts
                success = trigger_github_action('send_posts')
                
                # Answer the callback query to notify the user
                callback_id = data['callback_query']['id']
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                requests.post(url, json={
                    "callback_query_id": callback_id,
                    "text": "Retrieving the last 10 posts... Please wait a moment."
                })
                
                if success:
                    return jsonify({"status": "success", "message": "GitHub Action triggered"}), 200
                else:
                    return jsonify({"status": "error", "message": "Failed to trigger GitHub Action"}), 500
        
        return jsonify({"status": "success", "message": "Webhook received"}), 200
    
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "healthy"}), 200

def main():
    """Run the Flask app."""
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False)

if __name__ == "__main__":
    main() 