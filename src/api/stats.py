#!/usr/bin/env python3
"""
Simple API for Shorpy Scraper monitoring and statistics.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from flask import Flask, jsonify, request, render_template

from src.database.models import storage
from src.database.connection import db_pool
from src.utils.metrics import metrics
from src.config import config
from src.utils.error_handler import safe_execute

# Set up logger
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))

@app.route('/', methods=['GET'])
def dashboard():
    """Render the dashboard page."""
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for the API."""
    try:
        # Check database connection
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            db_status = cursor.fetchone() is not None
        
        # Check configuration
        config_status = bool(config.get("telegram_bot_token")) and bool(config.get("telegram_channel_id"))
        
        # Get database statistics
        post_count = storage.get_post_count()
        
        return jsonify({
            "status": "healthy" if db_status and config_status else "degraded",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "database": {
                    "status": "connected" if db_status else "disconnected",
                    "connection_pool": db_pool.get_stats(),
                    "post_count": post_count
                },
                "config": {
                    "status": "valid" if config_status else "incomplete",
                    "critical_keys_present": config_status
                }
            }
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }), 500

@app.route('/metrics', methods=['GET'])
def get_metrics():
    """Get application metrics."""
    try:
        # Get metrics from the metrics collector
        counter_metrics = metrics.counters
        gauge_metrics = metrics.gauges
        timer_metrics = {name: metrics.get_timer_stats(name) for name in metrics.timers}
        
        # Get metrics from database
        time_range = request.args.get('range', 'day')
        
        if time_range == 'hour':
            from_time = datetime.now() - timedelta(hours=1)
        elif time_range == 'day':
            from_time = datetime.now() - timedelta(days=1)
        elif time_range == 'week':
            from_time = datetime.now() - timedelta(weeks=1)
        elif time_range == 'month':
            from_time = datetime.now() - timedelta(days=30)
        else:
            from_time = datetime.now() - timedelta(days=1)  # Default to 1 day
        
        # Get post metrics from DB
        posts_added = len(storage.get_metrics("posts.added", from_time=from_time))
        posts_published = len(storage.get_metrics("posts.published", from_time=from_time))
        
        # Get database stats
        db_stats = db_pool.get_stats()
        
        return jsonify({
            "timestamp": datetime.now().isoformat(),
            "time_range": time_range,
            "metrics": {
                "counters": counter_metrics,
                "gauges": gauge_metrics,
                "timers": timer_metrics,
                "posts": {
                    "total": storage.get_post_count(),
                    "added_in_period": posts_added,
                    "published_in_period": posts_published
                },
                "database": db_stats
            }
        }), 200
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/posts/latest', methods=['GET'])
def get_latest_posts():
    """Get the latest posts from the database."""
    try:
        limit = int(request.args.get('limit', 10))
        published_only = request.args.get('published', 'false').lower() == 'true'
        
        posts = storage.get_latest_posts(limit=limit, published_only=published_only)
        
        return jsonify({
            "count": len(posts),
            "posts": posts
        }), 200
    except Exception as e:
        logger.error(f"Error getting latest posts: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/posts/unpublished', methods=['GET'])
def get_unpublished_posts():
    """Get unpublished posts from the database."""
    try:
        limit = int(request.args.get('limit', 10))
        
        posts = storage.get_unpublished_posts(limit=limit)
        
        return jsonify({
            "count": len(posts),
            "posts": posts
        }), 200
    except Exception as e:
        logger.error(f"Error getting unpublished posts: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get application configuration (safe version)."""
    try:
        # Get all configuration but filter out sensitive values
        config_data = config.get_all()
        
        # Replace sensitive values with asterisks
        sensitive_keys = ['telegram_bot_token', 'github_token']
        for key in sensitive_keys:
            if key in config_data:
                if config_data[key]:
                    config_data[key] = '********'
        
        return jsonify({
            "config": config_data
        }), 200
    except Exception as e:
        logger.error(f"Error getting configuration: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

def run_api_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the API server."""
    app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get configuration
    host = config.get("api_host", "0.0.0.0")
    port = int(config.get("api_port", 5000))
    debug = config.get("api_debug", False)
    
    # Run the server
    logger.info(f"Starting API server on {host}:{port}")
    run_api_server(host=host, port=port, debug=debug) 