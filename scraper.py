import requests
from bs4 import BeautifulSoup
from models import storage
import re

class ShorpyScraper:
    BASE_URL = "https://www.shorpy.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    def get_latest_posts(self):
        try:
            print(f"Fetching posts from {self.BASE_URL}")
            headers = {'User-Agent': self.USER_AGENT}
            response = requests.get(self.BASE_URL, headers=headers)
            response.raise_for_status()
            
            print(f"Response status: {response.status_code}")
            print(f"Response length: {len(response.text)} bytes")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find posts with correct div class "node"
            all_posts = soup.find_all('div', class_='node')
            print(f"Found {len(all_posts)} posts on the main page")
            
            # Get the last processed post URL from checkpoint
            last_post_url = storage.get_checkpoint('last_post_url')
            if last_post_url:
                print(f"Last processed post URL: {last_post_url}")
            
            # Flag to indicate if we've reached a previously processed post
            found_last_post = False if last_post_url else True  # If no last post, process all
            
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
                    
                    # Check if this is our last processed post
                    if last_post_url and post_url == last_post_url:
                        print(f"Found previously processed post: {post_url}")
                        found_last_post = True
                        break  # Stop processing, we've reached our last processed post
                    
                    # Check if post was already parsed or if we should skip due to checkpoint
                    if not found_last_post and not storage.is_post_parsed(post_url):
                        print(f"New post found: {post_url}")
                        
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
                        
                        posts.append({
                            'post_url': post_url,
                            'title': title,
                            'image_url': image_url,
                            'description': description
                        })
                    else:
                        print(f"Post already processed: {post_url}")
                except Exception as e:
                    print(f"Error parsing post: {str(e)}")
                    continue
            
            return posts
            
        except Exception as e:
            print(f"Error scraping Shorpy: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
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
                    
                    posts.append({
                        'post_url': post_url,
                        'title': title,
                        'image_url': image_url,
                        'description': description
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
        try:
            storage.add_post(post_data)
            print(f"Marked post as parsed: {post_data['title']}")
        except Exception as e:
            print(f"Error marking post as parsed: {str(e)}") 