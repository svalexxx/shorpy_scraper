#!/bin/bash
# Shorpy Scraper utility script

# Set up colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Ensure script stops on errors
set -e

# Setup default report bot
REPORT_BOT="@tessssto_bot"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    VENV_ACTIVATED=true
fi

# Helper function to display usage
function show_help {
    echo -e "${YELLOW}Shorpy Scraper Utility Script${NC}"
    echo ""
    echo "Usage: ./shorpy.sh [command]"
    echo ""
    echo "Commands:"
    echo "  run               Run the scraper once and exit"
    echo "  run-silent        Run the scraper in silent mode"
    echo "  run-report        Run the scraper once and send a report to $REPORT_BOT"
    echo "  schedule          Run on a 12-hour schedule"
    echo "  schedule-report   Run on a 12-hour schedule with reports to $REPORT_BOT"
    echo "  docker-build      Build the Docker image"
    echo "  docker-run        Run the scraper in a Docker container"
    echo "  docker-run-report Run in a Docker container with reports to $REPORT_BOT"
    echo "  docker-compose    Run with docker-compose"
    echo "  status            Send a status report"
    echo "  status-bot        Send a status report to $REPORT_BOT"
    echo "  health            Run a health check"
    echo "  cleanup           Clean up temporary files"
    echo "  test              Test the connection to Telegram"
    echo "  async-test        Test the asynchronous scraper"
    echo "  update            Update dependencies"
    echo "  help              Show this help message"
    echo ""
}

# Check command line arguments
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

case "$1" in
    run)
        echo -e "${GREEN}Running scraper once...${NC}"
        python main.py --run-once
        ;;
    run-silent)
        echo -e "${GREEN}Running scraper in silent mode...${NC}"
        python main.py --run-once --silent
        ;;
    run-report)
        echo -e "${GREEN}Running scraper once with report to $REPORT_BOT...${NC}"
        python main.py --run-once --report-to $REPORT_BOT
        ;;
    schedule)
        echo -e "${GREEN}Running on a 12-hour schedule...${NC}"
        python main.py --schedule
        ;;
    schedule-report)
        echo -e "${GREEN}Running on a 12-hour schedule with reports to $REPORT_BOT...${NC}"
        python main.py --schedule --report-to $REPORT_BOT
        ;;
    docker-build)
        echo -e "${GREEN}Building Docker image...${NC}"
        docker build -t shorpy-scraper .
        ;;
    docker-run)
        echo -e "${GREEN}Running in Docker container...${NC}"
        docker run -d --name shorpy-scraper \
            -v $(pwd)/data/scraped_posts:/app/data/scraped_posts \
            -v $(pwd)/shorpy_data.db:/app/shorpy_data.db \
            -v $(pwd)/.env:/app/.env \
            shorpy-scraper
        echo -e "${GREEN}Container started. View logs with:${NC} docker logs -f shorpy-scraper"
        ;;
    docker-run-report)
        echo -e "${GREEN}Running in Docker container with reports to $REPORT_BOT...${NC}"
        docker run -d --name shorpy-scraper \
            -v $(pwd)/data/scraped_posts:/app/data/scraped_posts \
            -v $(pwd)/shorpy_data.db:/app/shorpy_data.db \
            -v $(pwd)/.env:/app/.env \
            shorpy-scraper python main.py --schedule --silent --report-to $REPORT_BOT
        echo -e "${GREEN}Container started. View logs with:${NC} docker logs -f shorpy-scraper"
        ;;
    docker-compose)
        echo -e "${GREEN}Running with docker-compose...${NC}"
        docker-compose up -d
        echo -e "${GREEN}Container started. View logs with:${NC} docker-compose logs -f"
        ;;
    status)
        echo -e "${GREEN}Sending status report...${NC}"
        python -m src.utils.monitor --report
        ;;
    status-bot)
        echo -e "${GREEN}Sending status report to $REPORT_BOT...${NC}"
        python -m src.utils.monitor --report --target-bot $REPORT_BOT
        ;;
    health)
        echo -e "${GREEN}Running health check...${NC}"
        python -m src.utils.monitor --health-check
        ;;
    cleanup)
        echo -e "${GREEN}Cleaning up temporary files...${NC}"
        python -m src.utils.monitor --cleanup
        ;;
    test)
        echo -e "${GREEN}Testing Telegram connection...${NC}"
        python -m tests.test_channel
        ;;
    async-test)
        echo -e "${GREEN}Testing asynchronous scraper...${NC}"
        python -m src.scraper.async_scraper
        ;;
    update)
        echo -e "${GREEN}Updating dependencies...${NC}"
        pip install -r requirements.txt --upgrade
        ;;
    help)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac

# Deactivate virtual environment if it was activated
if [ "$VENV_ACTIVATED" = true ]; then
    deactivate
fi

exit 0 