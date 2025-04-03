#!/usr/bin/env python3
"""
Asynchronous scraper for Shorpy.com
Provides better performance with concurrent image downloads
"""

import asyncio
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
import logging
import os
import tempfile
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.database.models import storage
from src.database.connection import db_pool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('async_scraper')

class AsyncShorpyScraper:
    """Asynchronous implementation of the Shorpy scraper"""
    
    BASE_URL = "https://www.shorpy.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    def __init__(self, concurrent_downloads: int = 3):
        """Initialize the scraper
        
        Args:
            concurrent_downloads: Maximum number of concurrent image downloads
        """
        self.headers = {'User-Agent': self.USER_AGENT}
        self.semaphore = asyncio.Semaphore(concurrent_downloads)
        self.session = None  # Will be initialized in get_latest_posts
        
    async def get_latest_posts(self) -> List[Dict[str, Any]]:
        """Fetch and parse the latest posts from Shorpy.com
        
        Returns:
            List of post dictionaries with metadata
        """
        try:
            logger.info(f"Fetching posts from {self.BASE_URL}")
            
            # Initialize aiohttp session
            async with aiohttp.ClientSession(headers=self.headers) as self.session:
                # Fetch main page
                async with self.session.get(self.BASE_URL) as response:
                    if response.status != 200:
                        logger.error(f"Error fetching main page: HTTP {response.status}")
                        return []
                    
                    html = await response.text()
                    logger.info(f"Response length: {len(html)} bytes")
                    
                    # Parse the HTML
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find posts with correct div class "node"
                    all_posts = soup.find_all('div', class_='node')
                    logger.info(f"Found {len(all_posts)} posts on the main page")
                    
                    # Get the last processed post URL from checkpoint
                    last_post_url = storage.get_checkpoint('last_post_url')
                    if last_post_url:
                        logger.info(f"Last processed post URL: {last_post_url}")
                    
                    # Flag to indicate if we've reached a previously processed post
                    found_last_post = False if last_post_url else True  # If no last post, process all
                    
                    # Parse all posts
                    raw_posts = []
                    for post in all_posts:
                        try:
                            # Get the title and URL
                            title_elem = post.find('h2', class_='nodetitle')
                            if not title_elem:
                                logger.warning("Could not find title element, skipping")
                                continue
                                
                            link_elem = title_elem.find('a')
                            if not link_elem:
                                logger.warning("Could not find link element, skipping")
                                continue
                                
                            title = link_elem.text.strip()
                            post_url = link_elem['href']
                            if not post_url.startswith('http'):
                                post_url = self.BASE_URL + post_url
                            
                            logger.info(f"Checking post URL: {post_url}")
                            
                            # Check if this is our last processed post
                            if last_post_url and post_url == last_post_url:
                                logger.info(f"Found previously processed post: {post_url}")
                                found_last_post = True
                                break  # Stop processing, we've reached our last processed post
                            
                            # Check if post was already parsed or if we should skip due to checkpoint
                            if not found_last_post or not storage.is_post_parsed(post_url):
                                # Parse the post data
                                post_data = await self._parse_post(post, post_url, title)
                                if post_data:
                                    raw_posts.append(post_data)
                            else:
                                logger.info(f"Post already processed: {post_url}")
                                
                        except Exception as e:
                            logger.error(f"Error parsing post: {str(e)}")
                            continue
                    
                    # Process images concurrently
                    if raw_posts:
                        tasks = [self._process_post_image(post) for post in raw_posts]
                        processed_posts = await asyncio.gather(*tasks)
                        
                        # Filter out None values (failed posts)
                        return [post for post in processed_posts if post is not None]
                    else:
                        return []
                    
        except Exception as e:
            logger.error(f"Error scraping Shorpy: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _parse_post(self, post_element, post_url: str, title: str) -> Optional[Dict[str, Any]]:
        """Parse a post element from BeautifulSoup
        
        Args:
            post_element: BeautifulSoup element for the post
            post_url: URL of the post
            title: Title of the post
            
        Returns:
            Dictionary with post data or None if parsing failed
        """
        try:
            # Find the image element (within content div)
            content_div = post_element.find('div', class_='content')
            if not content_div:
                logger.warning("Could not find content div, skipping")
                return None
                
            # Find image in content div
            img_elem = content_div.find('img')
            image_url = None
            if img_elem and 'src' in img_elem.attrs:
                # Get the preview URL
                preview_url = img_elem['src']
                if not preview_url.startswith('http'):
                    preview_url = self.BASE_URL + preview_url
                
                # We'll process the image later, just store the preview URL for now
                image_url = preview_url
            
            # Get the description (paragraph after the image)
            description = ""
            desc_p = content_div.find('p')
            if desc_p:
                description = desc_p.text.strip()
            
            logger.info(f"Parsed post: {title}")
            
            # Check if the post was previously published to Telegram
            is_published = storage.is_post_published(post_url)
            
            return {
                'post_url': post_url,
                'title': title,
                'preview_url': image_url,  # The original preview URL
                'image_url': None,  # Will be populated later
                'description': description,
                'is_published': is_published
            }
        except Exception as e:
            logger.error(f"Error parsing post element: {str(e)}")
            return None
    
    async def _process_post_image(self, post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a post's image URL, trying to find the full-size version
        
        Args:
            post: Post dictionary with metadata
            
        Returns:
            Updated post dictionary or None if processing failed
        """
        try:
            if not post.get('preview_url'):
                # No image URL, nothing to process
                return post
                
            # Use a semaphore to limit concurrent image processing
            async with self.semaphore:
                preview_url = post['preview_url']
                
                # Try multiple approaches to get a valid image URL
                # 1. Try removing .preview from the URL
                image_url = preview_url
                if '.preview.' in preview_url:
                    full_size_url = preview_url.replace('.preview.jpg', '.jpg')
                    logger.info(f"Trying full-size image URL: {full_size_url}")
                    
                    # Check if the URL is valid
                    try:
                        async with self.session.head(full_size_url, timeout=5) as head_response:
                            if head_response.status == 200:
                                image_url = full_size_url
                                logger.info(f"Valid full-size image URL found: {image_url}")
                            else:
                                logger.warning(f"Full-size image URL not found, status: {head_response.status}")
                                image_url = preview_url
                                logger.info(f"Using preview URL instead: {image_url}")
                    except Exception as e:
                        logger.error(f"Error checking full-size URL: {str(e)}")
                        image_url = preview_url
                        logger.info(f"Using preview URL instead: {image_url}")
                
                # Set the final image URL
                post['image_url'] = image_url
                return post
                
        except Exception as e:
            logger.error(f"Error processing post image: {str(e)}")
            # Still return the post, just without the processed image URL
            post['image_url'] = post.get('preview_url')
            return post
    
    async def get_test_posts(self, num_posts: int = 2) -> List[Dict[str, Any]]:
        """Get a specific number of posts for testing, ignoring whether they've been processed before
        
        Args:
            num_posts: Number of posts to retrieve
            
        Returns:
            List of post dictionaries
        """
        try:
            logger.info(f"Fetching {num_posts} posts for testing from {self.BASE_URL}")
            
            # Initialize aiohttp session
            async with aiohttp.ClientSession(headers=self.headers) as self.session:
                # Fetch main page
                async with self.session.get(self.BASE_URL) as response:
                    if response.status != 200:
                        logger.error(f"Error fetching main page: HTTP {response.status}")
                        return []
                    
                    html = await response.text()
                    logger.info(f"Response length: {len(html)} bytes")
                    
                    # Parse the HTML
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find posts with correct div class "node"
                    all_posts = soup.find_all('div', class_='node')
                    logger.info(f"Found {len(all_posts)} posts on the main page")
                    
                    # Parse specified number of posts
                    raw_posts = []
                    for post in all_posts[:num_posts]:
                        try:
                            # Get the title and URL
                            title_elem = post.find('h2', class_='nodetitle')
                            if not title_elem:
                                logger.warning("Could not find title element, skipping")
                                continue
                                
                            link_elem = title_elem.find('a')
                            if not link_elem:
                                logger.warning("Could not find link element, skipping")
                                continue
                                
                            title = link_elem.text.strip()
                            post_url = link_elem['href']
                            if not post_url.startswith('http'):
                                post_url = self.BASE_URL + post_url
                            
                            logger.info(f"Processing test post: {post_url}")
                            
                            # Parse the post data
                            post_data = await self._parse_post(post, post_url, title)
                            if post_data:
                                raw_posts.append(post_data)
                                
                        except Exception as e:
                            logger.error(f"Error parsing test post: {str(e)}")
                            continue
                    
                    # Process images concurrently
                    if raw_posts:
                        tasks = [self._process_post_image(post) for post in raw_posts]
                        processed_posts = await asyncio.gather(*tasks)
                        
                        # Filter out None values (failed posts)
                        return [post for post in processed_posts if post is not None]
                    else:
                        return []
                    
        except Exception as e:
            logger.error(f"Error getting test posts: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def mark_as_parsed(self, post: Dict[str, Any]) -> bool:
        """Mark a post as parsed in the database
        
        Args:
            post: Post dictionary with metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            storage.add_post(post)
            logger.info(f"Marked post as parsed: {post['title']}")
            return True
        except Exception as e:
            logger.error(f"Error marking post as parsed: {str(e)}")
            return False
    
    def mark_as_published(self, post: Dict[str, Any]) -> bool:
        """Mark a post as published to Telegram
        
        Args:
            post: Post dictionary with metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            success = storage.mark_post_published(post['post_url'])
            if success:
                logger.info(f"Marked post as published: {post['title']}")
            else:
                logger.error(f"Failed to mark post as published: {post['title']}")
            return success
        except Exception as e:
            logger.error(f"Error marking post as published: {str(e)}")
            return False

# Example usage
async def test_scraper():
    scraper = AsyncShorpyScraper()
    posts = await scraper.get_latest_posts()
    print(f"Found {len(posts)} posts")
    for post in posts:
        print(f"Title: {post['title']}")
        print(f"URL: {post['post_url']}")
        print(f"Image: {post['image_url']}")
        print("---")

if __name__ == "__main__":
    asyncio.run(test_scraper()) 