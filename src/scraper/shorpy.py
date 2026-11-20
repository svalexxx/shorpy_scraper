import requests
from bs4 import BeautifulSoup
from src.database.models import storage
import re
import time

class ShorpyScraper:
    BASE_URL = "https://www.shorpy.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    def _extract_post_id(self, post_url):
        """Extract post ID from URL.
        
        Args:
            post_url: URL of the post
            
        Returns:
            str: Post ID or None if not found
        """
        try:
            # Extract post ID from URL (e.g., https://www.shorpy.com/node/27789 -> 27789)
            match = re.search(r'/node/(\d+)', post_url)
            if match:
                return match.group(1)
        except Exception as e:
            print(f"Error extracting post ID: {str(e)}")
        return None
    
    def _fetch_front_page(self, attempts=3, timeout=30):
        """Fetch the Shorpy front page with a timeout and retries."""
        headers = {'User-Agent': self.USER_AGENT}
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                response = requests.get(self.BASE_URL, headers=headers, timeout=timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                last_error = e
                print(f"Fetch attempt {attempt}/{attempts} failed: {str(e)}")
                if attempt < attempts:
                    time.sleep(5 * attempt)
        raise last_error

    def get_latest_posts(self):
        try:
            print(f"Fetching posts from {self.BASE_URL}")
            response = self._fetch_front_page()
            
            print(f"Response status: {response.status_code}")
            print(f"Response length: {len(response.text)} bytes")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find posts with correct div class "node"
            all_posts = soup.find_all('div', class_='node')
            print(f"Found {len(all_posts)} posts on the main page")
            
            # Get the last processed post URL and time from checkpoints
            last_post_url = storage.get_checkpoint('last_post_url')
            last_processed_time = storage.get_checkpoint('last_processed_time')
            
            if last_post_url:
                print(f"Last processed post URL: {last_post_url}")
            if last_processed_time:
                print(f"Last processed time: {last_processed_time}")
            
            posts = []
            for post in all_posts:
                try:
                    # Get the title and URL
                    title_elem = post.find('h2', class_='nodetitle')
                    if not title_elem:
                        print("Could not find title element, skipping")
                        continue
                        
                    link_elem = title_elem.find('a')
                    if not link_elem:
                        print("Could not find link element, skipping")
                        continue
                        
                    title = link_elem.text.strip()
                    post_url = link_elem['href']
                    if not post_url.startswith('http'):
                        post_url = self.BASE_URL + post_url
                    
                    print(f"Checking post URL: {post_url}")
                    
                    # Extract post ID from URL
                    post_id = self._extract_post_id(post_url)
                    if not post_id:
                        print(f"Could not extract post ID from URL: {post_url}")
                        continue
                    
                    # Check if post was already parsed
                    if storage.is_post_parsed(post_url):
                        print(f"Post already processed: {post_url}")
                        continue
                    
                    # Find the image element (within content div)
                    content_div = post.find('div', class_='content')
                    if not content_div:
                        print("Could not find content div, skipping")
                        continue
                        
                    # Find image in content div
                    img_elem = content_div.find('img')
                    image_url = None
                    if img_elem and 'src' in img_elem.attrs:
                        # Get the preview URL
                        preview_url = img_elem['src']
                        if not preview_url.startswith('http'):
                            preview_url = self.BASE_URL + preview_url
                        
                        # Try multiple approaches to get a valid image URL
                        # 1. Try removing .preview from the URL
                        if '.preview.' in preview_url:
                            full_size_url = preview_url.replace('.preview.jpg', '.jpg')
                            print(f"Trying full-size image URL: {full_size_url}")
                            
                            # Check if the URL is valid
                            try:
                                head_response = requests.head(full_size_url, timeout=5)
                                if head_response.status_code == 200:
                                    image_url = full_size_url
                                    print(f"Valid full-size image URL found: {image_url}")
                                else:
                                    print(f"Full-size image URL not found, status: {head_response.status_code}")
                                    image_url = preview_url
                                    print(f"Using preview URL instead: {image_url}")
                            except Exception as e:
                                print(f"Error checking full-size URL: {str(e)}")
                                image_url = preview_url
                                print(f"Using preview URL instead: {image_url}")
                        else:
                            # Just use the original URL
                            image_url = preview_url
                            print(f"Using original image URL: {image_url}")
                        
                        # Check if the image URL is valid
                        try:
                            head_response = requests.head(image_url, timeout=5)
                            if head_response.status_code != 200:
                                print(f"Warning: Image URL may not be valid, status: {head_response.status_code}")
                        except Exception as e:
                            print(f"Warning: Could not verify image URL: {str(e)}")
                    
                    # Get the description (paragraph after the image)
                    description = ""
                    desc_p = content_div.find('p')
                    if desc_p:
                        description = desc_p.text.strip()
                    
                    print(f"Parsed post: {title}")
                    if image_url:
                        print(f"Image URL: {image_url}")
                    
                    # Check if the post was previously published to Telegram
                    is_published = storage.is_post_published(post_url)
                    
                    posts.append({
                        'post_id': post_id,
                        'post_url': post_url,
                        'title': title,
                        'image_url': image_url,
                        'description': description,
                        'is_published': is_published
                    })
                except Exception as e:
                    print(f"Error parsing post: {str(e)}")
                    continue
            
            return posts
            
        except Exception as e:
            print(f"Error scraping Shorpy: {str(e)}")
            import traceback
            traceback.print_exc()
            # Surface the failure instead of pretending there are no new posts
            raise
    
    def get_test_posts(self, num_posts=2):
        """Get a specific number of posts for testing, ignoring whether they've been processed before."""
        try:
            print(f"Fetching {num_posts} posts for testing from {self.BASE_URL}")
            headers = {'User-Agent': self.USER_AGENT}
            response = requests.get(self.BASE_URL, headers=headers)
            response.raise_for_status()
            
            print(f"Response status: {response.status_code}")
            print(f"Response length: {len(response.text)} bytes")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find posts with correct div class "node"
            all_posts = soup.find_all('div', class_='node')
            print(f"Found {len(all_posts)} posts on the main page")
            
            posts = []
            for post in all_posts[:num_posts]:  # Only process the requested number of posts
                try:
                    # Get the title and URL
                    title_elem = post.find('h2', class_='nodetitle')
                    if not title_elem:
                        print("Could not find title element, skipping")
                        continue
                        
                    link_elem = title_elem.find('a')
                    if not link_elem:
                        print("Could not find link element, skipping")
                        continue
                        
                    title = link_elem.text.strip()
                    post_url = link_elem['href']
                    if not post_url.startswith('http'):
                        post_url = self.BASE_URL + post_url
                    
                    print(f"Processing test post: {post_url}")
                    
                    # Extract post ID from URL
                    post_id = self._extract_post_id(post_url)
                    if not post_id:
                        print(f"Could not extract post ID from URL: {post_url}")
                        continue
                    
                    # Find the image element (within content div)
                    content_div = post.find('div', class_='content')
                    if not content_div:
                        print("Could not find content div, skipping")
                        continue
                        
                    # Find image in content div
                    img_elem = content_div.find('img')
                    image_url = None
                    if img_elem and 'src' in img_elem.attrs:
                        # Get the preview URL
                        preview_url = img_elem['src']
                        if not preview_url.startswith('http'):
                            preview_url = self.BASE_URL + preview_url
                        
                        # Try multiple approaches to get a valid image URL
                        # 1. Try removing .preview from the URL
                        if '.preview.' in preview_url:
                            full_size_url = preview_url.replace('.preview.jpg', '.jpg')
                            print(f"Trying full-size image URL: {full_size_url}")
                            
                            # Check if the URL is valid
                            try:
                                head_response = requests.head(full_size_url, timeout=5)
                                if head_response.status_code == 200:
                                    image_url = full_size_url
                                    print(f"Valid full-size image URL found: {image_url}")
                                else:
                                    print(f"Full-size image URL not found, status: {head_response.status_code}")
                                    image_url = preview_url
                                    print(f"Using preview URL instead: {image_url}")
                            except Exception as e:
                                print(f"Error checking full-size URL: {str(e)}")
                                image_url = preview_url
                                print(f"Using preview URL instead: {image_url}")
                        else:
                            # Just use the original URL
                            image_url = preview_url
                            print(f"Using original image URL: {image_url}")
                        
                        # Check if the image URL is valid
                        try:
                            head_response = requests.head(image_url, timeout=5)
                            if head_response.status_code != 200:
                                print(f"Warning: Image URL may not be valid, status: {head_response.status_code}")
                        except Exception as e:
                            print(f"Warning: Could not verify image URL: {str(e)}")
                    
                    # Get the description (paragraph after the image)
                    description = ""
                    desc_p = content_div.find('p')
                    if desc_p:
                        description = desc_p.text.strip()
                    
                    print(f"Parsed post: {title}")
                    if image_url:
                        print(f"Image URL: {image_url}")
                    
                    # Check if the post was previously published to Telegram
                    is_published = storage.is_post_published(post_url)
                    
                    posts.append({
                        'post_id': post_id,
                        'post_url': post_url,
                        'title': title,
                        'image_url': image_url,
                        'description': description,
                        'is_published': is_published
                    })
                except Exception as e:
                    print(f"Error parsing post: {str(e)}")
                    continue
            
            return posts
            
        except Exception as e:
            print(f"Error scraping Shorpy: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def mark_as_parsed(self, post_data):
        """Mark a post as parsed in the database."""
        storage.add_post(post_data)
        print(f"Marked post as parsed: {post_data['title']}")
    
    def mark_as_published(self, post_data):
        """Mark a post as published in the database."""
        storage.mark_post_published(post_data['post_url'])
        print(f"Marked post as published: {post_data['title']}") 