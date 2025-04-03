#!/usr/bin/env python3
"""
Integration tests for the Shorpy Scraper application.
Tests the core functionality of the app without making actual network requests.
"""

import unittest
import sys
import os
import tempfile
import shutil
import asyncio
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import process_posts, save_post_locally

class TestIntegration(unittest.TestCase):
    """Integration tests for the Shorpy Scraper application"""
    
    def setUp(self):
        """Set up test environment with temporary directories"""
        # Create temporary directories for output and temp files
        self.temp_output_dir = tempfile.mkdtemp()
        self.temp_images_dir = tempfile.mkdtemp()
        
        # Save original directories
        self.original_output_dir = os.environ.get('OUTPUT_DIR')
        self.original_temp_dir = os.environ.get('TEMP_DIR')
        
        # Set environment variables to use temporary directories
        os.environ['OUTPUT_DIR'] = self.temp_output_dir
        os.environ['TEMP_DIR'] = self.temp_images_dir
        
        # Create a sample post for testing
        self.sample_post = {
            'post_url': 'https://example.com/test_post',
            'title': 'Test Post Title',
            'image_url': 'https://example.com/test_image.jpg',
            'description': 'This is a test post description.',
            'is_published': False
        }
    
    def tearDown(self):
        """Clean up temporary directories after tests"""
        # Remove temporary directories
        shutil.rmtree(self.temp_output_dir, ignore_errors=True)
        shutil.rmtree(self.temp_images_dir, ignore_errors=True)
        
        # Restore original environment variables
        if self.original_output_dir:
            os.environ['OUTPUT_DIR'] = self.original_output_dir
        else:
            os.environ.pop('OUTPUT_DIR', None)
            
        if self.original_temp_dir:
            os.environ['TEMP_DIR'] = self.original_temp_dir
        else:
            os.environ.pop('TEMP_DIR', None)
    
    def test_save_post_locally(self):
        """Test saving a post locally without network requests"""
        # Call the function to save post locally
        with patch('main.OUTPUT_DIR', self.temp_output_dir):
            result = save_post_locally(self.sample_post)
        
        # Check that files were created
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)  # Should return paths to HTML and JSON files
        
        # Check that both files exist
        self.assertTrue(os.path.exists(result[0]))
        self.assertTrue(os.path.exists(result[1]))
        
        # Check that HTML file contains post title
        with open(result[0], 'r') as f:
            html_content = f.read()
            self.assertIn(self.sample_post['title'], html_content)
    
    @patch('main.TelegramBot')
    @patch('main.ShorpyScraper')
    async def test_process_posts_no_posts(self, mock_scraper_class, mock_telegram_class):
        """Test processing posts when there are no posts to process"""
        # Setup mocks
        mock_scraper = mock_scraper_class.return_value
        mock_scraper.get_latest_posts.return_value = []
        
        mock_bot = mock_telegram_class.return_value
        mock_bot.send_no_posts_message.return_value = True
        
        # Call the function
        await process_posts()
        
        # Verify expected calls
        mock_scraper.get_latest_posts.assert_called_once()
        mock_telegram_class.assert_called_once()
        mock_bot.send_no_posts_message.assert_called_once()
    
    @patch('main.TelegramBot')
    @patch('main.ShorpyScraper')
    @patch('main.save_post_locally')
    async def test_process_posts_with_posts(self, mock_save_locally, mock_scraper_class, mock_telegram_class):
        """Test processing posts when there are posts to process"""
        # Setup mocks
        mock_scraper = mock_scraper_class.return_value
        mock_scraper.get_latest_posts.return_value = [self.sample_post]
        
        mock_bot = mock_telegram_class.return_value
        mock_bot.send_post.return_value = True
        
        mock_save_locally.return_value = ['/tmp/test.html', '/tmp/test.json']
        
        # Call the function
        await process_posts()
        
        # Verify expected calls
        mock_scraper.get_latest_posts.assert_called_once()
        mock_telegram_class.assert_called_once()
        mock_bot.send_post.assert_called_once()
        mock_save_locally.assert_called_once()
        mock_scraper.mark_as_parsed.assert_called_once()
        mock_scraper.mark_as_published.assert_called_once()
    
    @patch('main.TelegramBot')
    @patch('main.ShorpyScraper')
    @patch('main.save_post_locally')
    async def test_process_posts_with_error(self, mock_save_locally, mock_scraper_class, mock_telegram_class):
        """Test error handling during post processing"""
        # Setup mocks
        mock_scraper = mock_scraper_class.return_value
        mock_scraper.get_latest_posts.return_value = [self.sample_post]
        
        mock_bot = mock_telegram_class.return_value
        mock_bot.send_post.side_effect = Exception("Test error")
        
        mock_save_locally.return_value = ['/tmp/test.html', '/tmp/test.json']
        
        # Call the function
        await process_posts()
        
        # Verify expected calls
        mock_scraper.get_latest_posts.assert_called_once()
        mock_telegram_class.assert_called_once()
        mock_bot.send_post.assert_called_once()
        mock_save_locally.assert_called_once()
        mock_scraper.mark_as_parsed.assert_called_once()
        # Should not be called due to the error
        mock_scraper.mark_as_published.assert_not_called()

def run_async_tests():
    """Run async tests"""
    # Create a test suite with our async tests
    suite = unittest.TestSuite()
    suite.addTest(TestIntegration('test_process_posts_no_posts'))
    suite.addTest(TestIntegration('test_process_posts_with_posts'))
    suite.addTest(TestIntegration('test_process_posts_with_error'))
    
    # Run the tests
    runner = unittest.TextTestRunner()
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == '__main__':
    # Run synchronous tests
    sync_runner = unittest.TextTestRunner()
    sync_suite = unittest.TestLoader().loadTestsFromTestCase(TestIntegration)
    sync_result = sync_runner.run(unittest.TestSuite([
        test for test in sync_suite 
        if not test._testMethodName.startswith('test_process_posts')
    ]))
    
    # Run async tests using asyncio
    asyncio.run(run_async_tests()) 