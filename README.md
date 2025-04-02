# Shorpy Scraper and Telegram Bot

This project scrapes historic photos from [Shorpy.com](https://www.shorpy.com) and posts them to a Telegram channel.

## Features

- Scrapes the latest posts from Shorpy.com
- Saves posts locally as HTML and JSON files
- Sends posts to a Telegram channel or personal chat
- Creates an index.html file to browse saved posts
- Runs on a 12-hour schedule
- Checkpoint tracking for the last processed post
- Option to automatically delete files after processing
- Automatic cleanup of temporary image files
- Tracks published posts to avoid sending duplicates
- GitHub Actions integration for automated running
- Docker support for easy deployment
- Asynchronous image downloading for better performance
- Retry mechanism with exponential backoff for increased reliability
- System monitoring with status reports and health checks
- Silent mode to avoid sending test messages in production
- Interactive commands and buttons in Telegram
- "Last 10 posts" feature with inline buttons

## Installation

### Quick Install

For a guided installation process, use the installation script:

```bash
python -m src.utils.install
```

The script will:
1. Create necessary directories
2. Help you set up the .env file with your Telegram credentials
3. Create the database
4. Install dependencies
5. Set up automatic running (systemd service or cron job)
6. Test your setup

### Manual Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Create a Telegram bot:
   - Talk to [@BotFather](https://t.me/BotFather) on Telegram
   - Use the `/newbot` command to create a new bot
   - Copy the bot token provided by BotFather

3. Create a Telegram channel:
   - Create a new channel in Telegram
   - Add your bot as an administrator with posting privileges
   - Get the channel ID (can be found using the `getUpdates` API method)

4. Configure environment variables:
   - Create a `.env` file with your bot token and channel ID
   - Example:
     ```
     TELEGRAM_BOT_TOKEN=your_bot_token_here
     TELEGRAM_CHANNEL_ID=-1002647149349  # Your channel ID
     TELEGRAM_REPORT_CHANNEL_ID=29909617  # Your personal chat ID (for reports)
     ```

5. Create the database:
   ```bash
   python -m src.database.create_empty_db
   ```

6. Validate your setup:
   ```bash
   python -m src.utils.validate_setup
   ```

### Production Setup

For a robust production setup, consider:

1. **Systemd Service** (Linux):
   ```bash
   # Create a service file
   sudo nano /etc/systemd/system/shorpy-scraper.service
   
   # Add this content (adjust paths as needed):
   [Unit]
   Description=Shorpy Scraper Service
   After=network.target
   
   [Service]
   Type=simple
   User=your_username
   WorkingDirectory=/path/to/shorpy_scraper
   ExecStart=/path/to/python /path/to/shorpy_scraper/main.py --schedule --silent
   Restart=on-failure
   RestartSec=60
   
   [Install]
   WantedBy=multi-user.target
   
   # Enable and start the service
   sudo systemctl daemon-reload
   sudo systemctl enable shorpy-scraper.service
   sudo systemctl start shorpy-scraper.service
   ```

2. **Cron Job** (Unix/Linux):
   ```bash
   # Edit crontab
   crontab -e
   
   # Add this line to run every 6 hours
   0 */6 * * * cd /path/to/shorpy_scraper && /path/to/python main.py --run-once --silent
   ```

3. **Windows Task Scheduler**:
   - Open Task Scheduler
   - Create a new task
   - Set trigger to run daily, repeat every 6 hours
   - Action: Start a program
   - Program: `C:\path\to\python.exe`
   - Arguments: `C:\path\to\shorpy_scraper\main.py --run-once --silent`
   - Start in: `C:\path\to\shorpy_scraper`

4. **Docker** (recommended for consistent environment):
   ```bash
   # Build and run with docker-compose
   docker-compose up -d
   ```

## GitHub Actions setup (optional):

- Fork or push this repository to GitHub
- Add your Telegram bot token and channel ID as repository secrets:
  - Go to your repository → Settings → Secrets and variables → Actions
  - Create `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, and `TELEGRAM_REPORT_CHANNEL_ID` secrets
- The workflow will run automatically every 6 hours

### Health & Monitoring

For better monitoring in production:

1. **Enable reporting**:
   ```bash
   # Run with reporting to receive status reports
   python main.py --schedule --silent --report-to YOUR_CHAT_ID
   ```

2. **Set up periodic health checks**:
   ```bash
   # Add to your crontab
   0 12 * * * cd /path/to/shorpy_scraper && /path/to/python -m src.utils.monitor --health-check
   ```

3. **View logs**:
   ```bash
   # Check logs for errors
   tail -f logs/shorpy.log
   ```

4. **Cleanup**:
   ```bash
   # Clean up temporary files periodically
   0 0 * * 0 cd /path/to/shorpy_scraper && /path/to/python -m src.utils.monitor --cleanup
   ```

## Docker Deployment

You can easily run the application using Docker:

```bash
# Build the Docker image
docker build -t shorpy-scraper .

# Run the container
docker run -d --name shorpy-scraper \
  -v ./scraped_posts:/app/scraped_posts \
  -v ./shorpy_data.db:/app/shorpy_data.db \
  -v ./.env:/app/.env \
  shorpy-scraper
```

Or using docker-compose:

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f
```

## Usage

### Basic Usage

```bash
# Run once and exit
python main.py --run-once

# Run on a 12-hour schedule
python main.py --schedule

# Run in silent mode (no test messages)
python main.py --schedule --silent
```

### Advanced Options

```bash
# Reprocess existing posts
python main.py --reprocess

# Use a different channel ID
python main.py --channel -1002647149349

# Reprocess posts to a specific channel and exit
python main.py --reprocess --channel -1002647149349 --run-once

# Delete files after processing
python main.py --delete-files

# Display checkpoint information (last processed post)
python main.py --checkpoint

# Purge all files in the scraped_posts directory
python main.py --purge

# Test mode: process a specific number of posts (default: 2)
python main.py --test-posts 3

# Test mode with file deletion
python main.py --test-posts --delete-files

# Send the last 10 posts to the channel
python main.py --last-10-posts

# Send a button to show the last 10 posts
python main.py --send-button

# Run the bot in interactive mode (with commands)
python main.py --interactive
```

### Interactive Commands

The bot now supports interactive commands when run with `--interactive`:

- `/start` - Show welcome message and available commands
- `/help` - Show help message
- `/latest` - Show the last 10 posts
- `/status` - Show the current status

### Telegram Buttons

You can add interactive buttons to your channel:

1. **Last 10 Posts Button**: 
   - Send a button that users can click to see the last 10 posts
   - To add this button to your channel: `python main.py --send-button`
   - When users click the button, it will trigger the bot to send the last 10 posts

2. **GitHub Actions Integration**:
   - The button can trigger a GitHub Actions workflow to send posts
   - This works through a webhook that connects Telegram to GitHub Actions
   - To set up, use the provided `.github/workflows/last10posts.yml` workflow

### Webhook Deployment to Heroku

To enable the Telegram buttons to trigger GitHub Actions, you need to deploy the webhook to Heroku:

1. **Deploy to Heroku with one click**:

   [![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

   This will prompt you to enter:
   - Your Telegram Bot Token
   - A GitHub token with 'workflow' scope
   - Your GitHub username and repository name

2. **Or manually deploy**:
   ```bash
   # Login to Heroku
   heroku login

   # Create a new Heroku app
   heroku create shorpy-webhook

   # Set the necessary environment variables
   heroku config:set TELEGRAM_BOT_TOKEN=your_bot_token
   heroku config:set GITHUB_TOKEN=your_github_token
   heroku config:set GITHUB_REPO_OWNER=your_github_username
   heroku config:set GITHUB_REPO_NAME=shorpy_scraper

   # Push to Heroku
   git push heroku master
   ```

3. **Set up the Telegram webhook**:
   ```bash
   # Replace YOUR_BOT_TOKEN and YOUR_HEROKU_APP
   curl -F "url=https://YOUR_HEROKU_APP.herokuapp.com/webhook" https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook
   ```

4. **Verify the webhook setup**:
   ```bash
   # Check that the webhook is properly set
   curl https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo
   ```

5. **Send a test button to your channel**:
   ```bash
   python main.py --send-button
   ```

Now when users click the "Show Last 10 Posts" button, it will trigger the GitHub Actions workflow to send the posts.

### Monitoring

Shorpy Scraper includes a monitoring system that provides insights into application performance and database status.

#### Metrics Collection

The application automatically collects various metrics while running:
- **Counters**: Track operations like posts fetched, processed, published
- **Timers**: Measure how long key operations take
- **Gauges**: Track current values of various system metrics

#### API Server & Dashboard

A built-in API server and web dashboard provides real-time monitoring:

```bash
# Start the API server and dashboard
python main.py --api-server

# Specify a custom port
python main.py --api-server --api-port 8080
```

Once running, you can access:
- Dashboard UI: http://localhost:5000/
- Health check: http://localhost:5000/health
- Metrics data: http://localhost:5000/metrics
- Latest posts: http://localhost:5000/posts/latest
- Unpublished posts: http://localhost:5000/posts/unpublished

#### Error Handling

The application includes a robust error handling system:
- Automatic retries for intermittent errors
- Detailed error logging
- Safe execution modes to prevent catastrophic failures

### Testing

```bash
# Test the connection to Telegram
python test_channel.py

# Test the asynchronous scraper
python async_scraper.py
```

## File Structure

The project is organized into the following directory structure for better maintainability and separation of concerns:

```
shorpy_scraper/
├── src/                    # Source code
│   ├── scraper/            # Scraping logic
│   │   ├── shorpy.py       # Main scraper implementation
│   │   └── async_scraper.py # Asynchronous scraper implementation
│   ├── bot/                # Telegram bot
│   │   └── telegram_bot.py # Bot implementation
│   ├── database/           # Database operations
│   │   ├── models.py       # Database models
│   │   ├── init_db.py      # Database initialization
│   │   └── create_empty_db.py # Database creation script
│   └── utils/              # Utility functions
│       ├── monitor.py      # Monitoring and reporting
│       ├── commit_db.py    # Database commit utility
│       └── validate_setup.py # Setup validation
├── tests/                  # Test files
├── scripts/                # Shell scripts
│   └── shorpy.sh           # Main control script
├── data/                   # Data storage
│   ├── scraped_posts/      # Downloaded images
│   └── temp_images/        # Temporary files
├── logs/                   # Log files
├── main.py                 # Main entry point
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker configuration
└── docker-compose.yml      # Docker Compose configuration
```

### Key Components

- **src/scraper/**: Contains the main and asynchronous implementations of the Shorpy scraper
- **src/bot/**: Telegram bot implementation for sending photos to the channel
- **src/database/**: Database models and utilities for storing and retrieving data
- **src/utils/**: Utility scripts for monitoring, reporting, and maintenance
- **scripts/**: Shell scripts for common operations
- **data/**: Directories for storing downloaded images and temporary files
- **tests/**: Test files for different components

### Command-line Interface

The main script (`main.py`) can be run with various command-line arguments:

```
python main.py [options]
```

Options:
- `--run-once`: Run the scraper once and exit
- `--schedule`: Run on a schedule (default: every 12 hours)
- `--reprocess`: Reprocess already parsed (but not published) posts
- `--channel CHANNEL`: Set the Telegram channel ID to send posts to
- `--silent`: Skip sending test message on startup (for production)
- `--verbose`: Enable verbose logging
- `--delete-files`: Delete image files after processing
- `--purge`: Purge all database entries
- `--checkpoint`: Reset the last post checkpoint
- `--test-posts NUM`: Process a number of posts for testing
- `--report-to USERNAME`: Send a report to the specified username/chat ID

### Using the Shell Script

For convenience, a shell script is provided to run common operations:

```
./scripts/shorpy.sh [command]
```

Commands:
- `run`: Run the scraper once and exit
- `run-silent`: Run the scraper in silent mode
- `run-report`: Run the scraper once and send a report
- `schedule`: Run on a 12-hour schedule
- `docker-build`: Build the Docker image
- `docker-run`: Run the scraper in a Docker container
- `status`: Send a status report
- ...and more

## License

MIT 