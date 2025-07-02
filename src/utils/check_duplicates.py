#!/usr/bin/env python3
"""
Utility script to check for duplicate posts in the database
"""

from src.database.connection import db_pool
import logging

# Set up logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_duplicates():
    """Check for duplicate posts in the database"""
    try:
        # Check for duplicate post_urls
        cursor = db_pool.execute("""
            SELECT post_url, COUNT(*) as count
            FROM parsed_posts
            GROUP BY post_url
            HAVING COUNT(*) > 1
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            logger.info(f"Found {len(duplicates)} posts with duplicate URLs:")
            for post_url, count in duplicates:
                logger.info(f"URL: {post_url} appears {count} times")
                
                # Get details of the duplicates
                cursor = db_pool.execute("""
                    SELECT id, title, parsed_at, published
                    FROM parsed_posts
                    WHERE post_url = ?
                    ORDER BY parsed_at
                """, (post_url,))
                
                for row in cursor.fetchall():
                    logger.info(f"  ID: {row[0]}, Title: {row[1]}, Parsed: {row[2]}, Published: {row[3]}")
        else:
            logger.info("No duplicate post URLs found in the database")
            
        # Get total post count
        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts")
        total_posts = cursor.fetchone()[0]
        logger.info(f"\nTotal posts in database: {total_posts}")
        
        # Get published post count
        cursor = db_pool.execute("SELECT COUNT(*) FROM parsed_posts WHERE published = 1")
        published_posts = cursor.fetchone()[0]
        logger.info(f"Published posts: {published_posts}")
        
        # Get recent posts for inspection
        cursor = db_pool.execute("""
            SELECT post_url, title, parsed_at, published
            FROM parsed_posts
            ORDER BY parsed_at DESC
            LIMIT 5
        """)
        
        logger.info("\nMost recent posts:")
        for row in cursor.fetchall():
            logger.info(f"URL: {row[0]}")
            logger.info(f"Title: {row[1]}")
            logger.info(f"Parsed: {row[2]}")
            logger.info(f"Published: {row[3]}")
            logger.info("---")
            
    except Exception as e:
        logger.error(f"Error checking duplicates: {str(e)}")

if __name__ == "__main__":
    check_duplicates() 