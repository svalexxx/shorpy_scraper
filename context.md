# Shorpy Scraper Project Context

## Project Overview
This is a Python-based scraper for Shorpy.com that downloads historical images and posts them to a Telegram channel. The project consists of several key components:

1. Image Scraper (with both sync and async implementations)
2. Telegram Bot with robust error handling
3. SQLite Database Integration
4. Monitoring & Metrics System
5. Configuration Management

## Prerequisites
- Python 3.9+ (3.7+ minimum)
- SQLite 3.x
- System Requirements:
  - 1GB RAM minimum
  - 500MB disk space for database and images
  - Internet connectivity for scraping and Telegram
- Telegram Requirements:
  - Bot token (from @BotFather)
  - Channel admin rights for the bot
  - Chat ID for status reports
- Optional:
  - Docker for containerized deployment
  - GitHub account for webhook integration
  - Cron for scheduled tasks (Linux/macOS)

## Quick Start
1. Clone and Setup:
   ```bash
   # Clone the repository
   git clone https://github.com/username/shorpy_scraper.git
   cd shorpy_scraper

   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows

   # Install dependencies
   pip install -r requirements.txt
   ```

2. Configure:
   ```bash
   # Create .env file
   cp .env.example .env
   
   # Edit with your values
   nano .env  # or use any text editor
   ```

3. Validate Setup:
   ```bash
   # Run setup validation
   python main.py --setup
   
   # Test configuration
   python main.py --test --test-posts 1
   ```

4. Run:
   ```bash
   # Single run
   python main.py

   # Or scheduled mode
   python main.py --schedule --interval 60
   ```

5. Monitor:
   ```bash
   # Start monitoring API
   python src/api/stats.py
   
   # View dashboard at http://localhost:5000
   ```

## Project Structure

```
shorpy_scraper/
├── src/
│   ├── scraper/      # Image scraping logic (sync + async)
│   ├── bot/          # Telegram bot implementation
│   ├── database/     # Database models and connections
│   ├── api/          # Stats API and templates
│   └── utils/        # Utility functions
├── data/
│   ├── scraped_posts/  # Temporary storage for scraped content
│   └── temp_images/    # Temporary image storage
├── tests/            # Test suite
└── config/           # Configuration files
```

## Key Components

### Configuration System
- Configuration Sources (in priority order):
  1. Environment Variables
  2. JSON Configuration File (`config/config.json`)
  3. Default Values

- Critical Settings (Required):
  ```env
  TELEGRAM_BOT_TOKEN=your_bot_token
  TELEGRAM_CHANNEL_ID=your_channel_id
  TELEGRAM_REPORT_CHANNEL_ID=report_recipient_id
  GITHUB_TOKEN=your_github_token
  GITHUB_REPO_OWNER=your_username
  GITHUB_REPO_NAME=repo_name
  ```

- Optional Settings:
  1. Application Settings:
     ```env
     LOG_LEVEL=INFO
     TIMEZONE=UTC
     OUTPUT_DIR=scraped_posts
     TEMP_DIR=temp_images
     ```

  2. Scraper Settings:
     ```json
     {
       "shorpy_base_url": "https://www.shorpy.com",
       "user_agent": "Mozilla/5.0...",
       "request_timeout": 30,
       "max_retries": 3,
       "retry_delay": 1.0,
       "max_posts_per_run": 5
     }
     ```

  3. Database Settings:
     ```json
     {
       "db_path": "shorpy_data.db",
       "db_timeout": 20.0
     }
     ```

  4. Telegram Settings:
     ```json
     {
       "telegram_api_url": "https://api.telegram.org",
       "telegram_send_mode": "html",
       "telegram_disable_web_page_preview": false,
       "telegram_disable_notification": false
     }
     ```

  5. Schedule Settings:
     ```json
     {
       "schedule_interval_minutes": 60,
       "check_new_posts_interval_hours": 1
     }
     ```

- Configuration Management:
  - Auto-reload on changes
  - Type conversion for env vars
  - Validation of critical settings
  - Custom config file support
  - Centralized access via `config` singleton

### Scraper (src/scraper/)
- Two implementations:
  - `shorpy.py`: Synchronous implementation
  - `async_scraper.py`: Asynchronous version with better performance
- Features:
  - Smart image URL processing (preview → full-size conversion)
  - Checkpoint system to track last processed posts
  - Duplicate post detection
  - Configurable concurrent downloads
  - Robust error handling and retries

### Telegram Bot (src/bot/)
- Implemented in `telegram_bot.py`
- Features:
  - Robust error handling with retry mechanism
  - Exponential backoff for failed operations
  - Separate channels for posts and status reports
  - Detailed status reporting including:
    - Run statistics
    - Database metrics
    - Disk usage
    - Warnings and errors
  - Temporary file management for images
  - HTML formatting support
  - Caption truncation for long posts

### Database (src/database/)
- SQLite-based storage with connection pooling
- Schema:
  - `parsed_posts` table:
    - `id`: Auto-incrementing primary key
    - `post_url`: Unique URL of the post
    - `title`: Post title
    - `image_url`: URL of the image
    - `description`: Post description
    - `parsed_at`: Timestamp of parsing
    - `published`: Boolean flag for Telegram status
  - `checkpoints` table:
    - `id`: Auto-incrementing primary key
    - `key`: Unique checkpoint identifier
    - `value`: Checkpoint value
    - `updated_at`: Last update timestamp
  - `metrics` table:
    - `id`: Auto-incrementing primary key
    - `name`: Metric name
    - `value`: Numeric value
    - `timestamp`: Recording time
    - `metadata`: JSON metadata
- Connection management:
  - Thread-safe connection pool
  - Configurable timeout and max connections
  - Automatic retry on operational errors
- Key operations:
  - `add_post()`: Records new posts
  - `mark_post_published()`: Updates publication status
  - `get_checkpoint()`: Tracks last processed post
  - `is_post_parsed()`: Prevents duplicates
  - `get_latest_posts()`: Retrieves recent posts
  - `get_unpublished_posts()`: Gets pending posts

### Utilities (src/utils/)
- Error handling (`error_handler.py`)
- Duplicate checking (`check_duplicates.py`)
- Setup validation (`validate_setup.py`)
- Metrics collection (`metrics.py`)
- Monitoring tools (`monitor.py`)

### API (src/api/)
- Flask-based monitoring API
- Endpoints:
  - `GET /`: Dashboard UI
  - `GET /health`: System health check
    - Database connection status
    - Configuration validation
    - Component health metrics
  - `GET /metrics`: Application metrics
    - Counter metrics
    - Gauge metrics
    - Timer statistics
    - Post statistics
    - Database performance
    - Configurable time ranges (hour/day/week/month)
  - `GET /posts/latest`: Recent posts
    - Optional filtering for published posts
    - Configurable limit
  - `GET /posts/unpublished`: Pending posts
    - Configurable limit
  - `GET /config`: Safe configuration view
    - Masked sensitive values
    - Current settings
- Features:
  - JSON response format
  - Error handling and status codes
  - Metric aggregation
  - Safe configuration exposure
- Integration with:
  - Database metrics
  - System monitoring
  - Configuration management

### Error Handling and Reliability
- Robust error handling system:
  - Retry mechanism with exponential backoff
  - Configurable retry attempts and delays
  - Exception categorization and filtering
  - Safe execution wrappers
  - Detailed error context tracking
- Decorators:
  - `@with_retry`: Automatic retry for transient failures
  - `@safe_execute`: Exception handling and logging
  - `@counted`: Operation counting for metrics
  - `@timed`: Performance timing

### Validation System
- Setup validation (`validate_setup.py`):
  - Python version check
  - Directory structure
  - Required files
  - Dependencies
  - Environment variables
  - Database schema
  - Network connectivity
  - File permissions
- Runtime validation (`validate.py`):
  - Telegram configuration
  - Filesystem access
  - Database connectivity
  - Critical settings
- Installation validation (`install.py`):
  - Directory creation
  - Environment setup
  - Database initialization
  - Dependencies installation
  - Service configuration
  - Cron job setup

### Monitoring and Metrics
- System monitoring (`monitor.py`):
  - Health checks
  - Status reporting
  - Resource usage tracking
  - Error detection
  - Performance metrics
- Metrics collection (`metrics.py`):
  - Counter metrics
    - Operation counts
    - Success/failure rates
    - Post processing stats
  - Timer metrics
    - Operation durations
    - Performance tracking
    - Statistical analysis
  - Gauge metrics
    - Resource utilization
    - Queue sizes
    - System state
- Persistence:
  - JSON-based storage
  - Regular updates
  - Historical tracking
  - Report generation

### Utilities
- Chat ID retrieval (`get_chat_id.py`)
  - Bot setup assistance
  - Channel configuration
  - Permission verification
- Webhook handler (`telegram_webhook.py`)
  - Button callbacks
  - GitHub Actions integration
  - Request verification
  - Event processing

### Metrics and Monitoring
- Comprehensive metrics collection:
  - Post processing statistics
  - Database operations timing
  - Storage usage tracking
  - Error rates and types
- Monitoring features:
  - Real-time status reports via Telegram
  - Detailed run statistics:
    - Start/end times and duration
    - Posts found/processed/sent
    - Database statistics
    - Disk usage metrics
  - Performance monitoring:
    - Database connection pool stats
    - Operation timing metrics
    - Resource utilization
  - Error tracking:
    - Operation failures
    - Network issues
    - Storage problems
- Reporting channels:
  - Main channel for posts
  - Separate channel for status reports
  - Configurable report recipients

### Command Line Interface
- Main script (`main.py`) options:
  - Setup and Validation:
    - `--setup`: Run setup and validation checks
    - `--no-telegram`: Disable Telegram functionality
    - `--silent`: Suppress test messages
  - Running Modes:
    - `--schedule`: Run as a scheduled job
    - `--interval N`: Set minutes between runs (default: 60)
    - `--test`: Run in test mode
    - `--test-posts N`: Number of test posts (default: 2)
    - `--force`: Process posts even if already parsed
  - File Management:
    - `--delete-files`: Delete files after processing
    - `--clean`: Clean temporary files
    - `--purge`: Purge all scraped files
  - Monitoring:
    - `--checkpoint`: Show checkpoint information
    - `--reprocess`: Reprocess unpublished posts
    - `--report-to USER`: Send reports to specific user

### Running the Scraper
1. Single Run Mode:
   ```bash
   # Basic run
   python main.py
   
   # Run with reporting
   python main.py --report-to @username
   
   # Test mode with 5 posts
   python main.py --test --test-posts 5
   ```

2. Scheduled Mode:
   ```bash
   # Run every hour
   python main.py --schedule
   
   # Run every 30 minutes
   python main.py --schedule --interval 30
   ```

3. Maintenance:
   ```bash
   # Clean temporary files
   python main.py --clean
   
   # Purge all scraped content
   python main.py --purge
   
   # Show last processed post
   python main.py --checkpoint
   ```

4. Testing and Setup:
   ```bash
   # Run setup and validation
   python main.py --setup
   
   # Test without sending to Telegram
   python main.py --test --no-telegram
   
   # Force reprocess unpublished posts
   python main.py --reprocess --force
   ```

## Development Notes

### Git Status
- Project uses Git for version control
- Main development happens on `master` branch
- Regular commits for scraper improvements and bug fixes

### Testing
- Test suite in `tests/` directory:
  - `test_integration.py`: End-to-end tests
    - Post processing workflow
    - Local file saving
    - Error handling
    - Mock network requests
  - `test_args.py`: Command line argument tests
    - Argument validation
    - Usage verification
    - Parser consistency
  - `test_channel.py`: Telegram channel tests
    - Bot connectivity
    - Channel permissions
    - Message sending
    - Image handling
    - Checkpoint verification
  - `test_send.py`: Direct API tests
    - Message sending via REST API
    - Basic connectivity checks

Running tests:
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_integration.py

# Run Telegram channel tests
python tests/test_channel.py [--checkpoint]

# Test message sending
python tests/test_send.py [CHAT_ID]
```

Test environment setup:
- Uses temporary directories for files
- Mocks network requests
- Simulates database operations
- Handles async operations
- Provides detailed error reporting

### Monitoring
- Comprehensive metrics collection
- Status reports via Telegram
- Disk usage tracking
- Database statistics
- Error reporting through separate channel

## Troubleshooting

### Database Issues
1. "Post ID missing" errors:
   - Check database schema version
   - Run database migrations:
     ```bash
     python src/database/create_empty_db.py --force
     ```
   - Verify table structure:
     ```sql
     .tables
     .schema parsed_posts
     ```

2. Storage method mismatches:
   - Use correct method names:
     - `add_post()` instead of `mark_as_parsed`
     - `mark_post_published()` instead of `mark_as_published`
   - Check method signatures in `models.py`
   - Verify database connection pool settings

3. Database locked errors:
   - Reduce concurrent operations
   - Increase `db_timeout` in config
   - Check for stuck transactions
   - Run database maintenance:
     ```bash
     sqlite3 shorpy_data.db 'VACUUM;'
     ```

### Telegram Issues
1. Bot Authorization:
   - Verify bot token is valid
   - Check bot has required permissions:
     - Send Messages
     - Send Media
     - Edit Messages
     - Delete Messages
   - Ensure bot is channel admin

2. Message Sending Failures:
   - Check rate limiting (20 messages/minute)
   - Verify message format (HTML/Markdown)
   - Check media file sizes (< 50MB)
   - Ensure proper caption length (< 1024 chars)

3. Report Channel Issues:
   - Verify TELEGRAM_REPORT_CHANNEL_ID
   - Use `get_chat_id.py` to get correct ID:
     ```bash
     python src/utils/get_chat_id.py
     ```
   - Check bot's admin status
   - Test report sending:
     ```bash
     python main.py --test --report-to YOUR_CHAT_ID
     ```

### Scraper Issues
1. Image Download Failures:
   - Check network connectivity
   - Verify image URLs:
     ```bash
     curl -I IMAGE_URL
     ```
   - Check temp directory permissions:
     ```bash
     ls -la temp_images/
     ```
   - Clear temp files:
     ```bash
     python main.py --clean
     ```

2. Rate Limiting:
   - Increase retry delays
   - Reduce concurrent downloads
   - Use proxy rotation (if configured)
   - Check server response headers

3. Parsing Errors:
   - Update user agent string
   - Check HTML structure changes
   - Verify selector patterns
   - Enable debug logging:
     ```bash
     LOG_LEVEL=DEBUG python main.py
     ```

### System Issues
1. Disk Space:
   - Monitor usage:
     ```bash
     du -sh data/* temp_images/*
     ```
   - Clean old files:
     ```bash
     python main.py --purge
     ```
   - Configure auto-cleanup

2. Memory Usage:
   - Reduce batch sizes
   - Monitor with:
     ```bash
     ps aux | grep python
     ```
   - Check for memory leaks
   - Use async implementation

3. Performance:
   - Use connection pooling
   - Enable async scraping
   - Optimize database indexes
   - Monitor metrics endpoint

### Docker Issues
1. Container Startup:
   - Check logs:
     ```bash
     docker-compose logs -f
     ```
   - Verify volume mounts
   - Check environment variables
   - Ensure proper permissions

2. Volume Persistence:
   - Check mount points
   - Verify file ownership
   - Monitor disk usage
   - Backup data volumes

3. Network Issues:
   - Check container networking
   - Verify port mappings
   - Test container DNS
   - Check proxy settings

## Docker Support
- Dockerfile and docker-compose.yml available
- Build: `docker-compose build`
- Run: `docker-compose up`

## Performance Considerations
- Use async scraper for better performance
- Configure concurrent downloads based on system capabilities
- Monitor disk usage for scraped posts
- Regular database maintenance recommended
- Database optimizations:
  - Connection pooling for better resource usage
  - Retry mechanism for transient failures
  - Indexed queries for better performance
  - Regular vacuum operations recommended 

### Docker Deployment
- Container Configuration:
  - Base image: `python:3.9-slim`
  - System dependencies: gcc
  - Working directory: `/app`
  - Environment variables:
    - `PYTHONPATH=/app`
    - `TZ=Asia/Nicosia`
  - Volumes:
    - `./data/scraped_posts:/app/data/scraped_posts`
    - `./data/temp_images:/app/data/temp_images`
    - `./shorpy_data.db:/app/shorpy_data.db`
    - `./.env:/app/.env`

- Deployment Options:
  1. Using Docker directly:
     ```bash
     # Build the image
     docker build -t shorpy-scraper .
     
     # Run the container
     docker run -d \
       -v $(pwd)/data:/app/data \
       -v $(pwd)/shorpy_data.db:/app/shorpy_data.db \
       -v $(pwd)/.env:/app/.env \
       --name shorpy-scraper \
       shorpy-scraper
     ```

  2. Using Docker Compose:
     ```bash
     # Start the service
     docker-compose up -d
     
     # View logs
     docker-compose logs -f
     
     # Stop the service
     docker-compose down
     ```

- Container Features:
  - Automatic restart policy: `unless-stopped`
  - Volume persistence for:
    - Scraped posts
    - Temporary images
    - Database
    - Environment configuration
  - Timezone configuration
  - Silent mode with reporting
  - Scheduled execution 

### API Documentation
- Stats API (`src/api/stats.py`):
  - Server Configuration:
    - Default host: `0.0.0.0`
    - Default port: `5000`
    - Configuration via environment:
      - `API_HOST`: Server host
      - `API_PORT`: Server port
      - `API_DEBUG`: Debug mode

  - Endpoints:
    1. Dashboard
       - `GET /`
       - Web interface for monitoring
       - Renders `templates/index.html`

    2. Health Check
       - `GET /health`
       - Returns:
         - System health status
         - Database connection status
         - Configuration validation
         - Component health metrics

    3. Metrics
       - `GET /metrics`
       - Parameters:
         - `range`: Time range (hour/day/week/month)
       - Returns:
         - Counter metrics
         - Gauge metrics
         - Timer statistics
         - Post metrics
         - Database stats

    4. Latest Posts
       - `GET /posts/latest`
       - Parameters:
         - `limit`: Number of posts (default: 10)
         - `published`: Filter by published status
       - Returns:
         - Post count
         - Post details

    5. Unpublished Posts
       - `GET /posts/unpublished`
       - Parameters:
         - `limit`: Number of posts (default: 10)
       - Returns:
         - Post count
         - Post details

    6. Configuration
       - `GET /config`
       - Returns:
         - Safe configuration view
         - Sensitive values masked

  - Running the API:
    ```bash
    # Direct execution
    python src/api/stats.py
    
    # With custom configuration
    API_HOST=localhost API_PORT=8080 API_DEBUG=true python src/api/stats.py
    ``` 