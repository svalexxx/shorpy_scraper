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

## Setup

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
     ```

5. GitHub Actions setup (optional):
   - Fork or push this repository to GitHub
   - Add your Telegram bot token and channel ID as repository secrets:
     - Go to your repository → Settings → Secrets and variables → Actions
     - Create `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID` secrets
   - The workflow will run automatically every 6 hours

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
```

### Monitoring

Use the monitoring script to check system health and get status reports:

```bash
# Send a basic status report to Telegram
python monitor.py --report

# Send a detailed status report
python monitor.py --report --detailed

# Run a health check and send alerts if issues found
python monitor.py --health-check

# Clean up orphaned temporary files
python monitor.py --cleanup
```

### Testing

```bash
# Test the connection to Telegram
python test_channel.py

# Test the asynchronous scraper
python async_scraper.py
```

## File Structure

- `main.py`: Main script
- `scraper.py`: Handles scraping Shorpy.com
- `async_scraper.py`: Asynchronous version of the scraper
- `telegram_bot.py`: Handles sending posts to Telegram
- `models.py`: Data storage
- `monitor.py`: System monitoring and health checks
- `test_channel.py`: Test Telegram connection
- `commit_db.py`: Helper script for committing database changes
- `scraped_posts/`: Directory for saved posts
- `temp_images/`: Temporary directory for downloaded images
- `.github/workflows/`: GitHub Actions workflow definitions
- `Dockerfile`: Docker configuration
- `docker-compose.yml`: Docker Compose configuration

## License

MIT 