#!/usr/bin/env python3
"""
Utility script to fix the published flag in the database.
This script will check for posts that have been sent to Telegram but are not marked as published.
"""

from src.database.connection import db_pool
import logging

# Set up logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_published_flags():
    """Fix the published flags in the database"""
    try:
        # Get total post count
        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts")
        total_posts = cursor.fetchone()[0]
        logger.info(f"Total posts in database: {total_posts}")
        
        # Get published post count
        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
        published_posts = cursor.fetchone()[0]
        logger.info(f"Currently marked as published: {published_posts}")
        
        # Get all posts ordered by parsed_at
        cursor = db_pool.execute("""
            SELECT id, post_url, title, parsed_at, published
            FROM parsed_posts
            ORDER BY parsed_at ASC
        """)
        
        posts = cursor.fetchall()
        logger.info(f"Found {len(posts)} posts to check")
        
        # Mark all posts as published since we know they've been sent
        # (the bot always sends posts when it processes them)
        updated = 0
        for post in posts:
            post_id, post_url, title, parsed_at, published = post
            if not published:
                logger.info(f"Marking post as published: {title} ({post_url})")
                db_pool.execute(
                    "UPDATE parsed_posts SET published = 1 WHERE id = ?",
                    (post_id,)
                )
                updated += 1
        
        logger.info(f"Updated {updated} posts to mark them as published")
        
        # Verify the changes
        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
        new_published_count = cursor.fetchone()[0]
        logger.info(f"Now marked as published: {new_published_count}")
        
    except Exception as e:
        logger.error(f"Error fixing published flags: {str(e)}")

if __name__ == "__main__":
    fix_published_flags() 