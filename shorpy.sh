#!/bin/bash
# Shorpy Scraper utility script

# Set up colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Ensure script stops on errors
set -e

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo -e "${GREEN}Activated virtual environment${NC}"
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
    echo "  schedule          Run on a 12-hour schedule"
    echo "  docker-build      Build the Docker image"
    echo "  docker-run        Run the scraper in a Docker container"
    echo "  docker-compose    Run with docker-compose"
    echo "  status            Send a status report"
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
    schedule)
        echo -e "${GREEN}Running on a 12-hour schedule...${NC}"
        python main.py --schedule
        ;;
    docker-build)
        echo -e "${GREEN}Building Docker image...${NC}"
        docker build -t shorpy-scraper .
        ;;
    docker-run)
        echo -e "${GREEN}Running in Docker container...${NC}"
        docker run -d --name shorpy-scraper \
            -v $(pwd)/scraped_posts:/app/scraped_posts \
            -v $(pwd)/shorpy_data.db:/app/shorpy_data.db \
            -v $(pwd)/.env:/app/.env \
            shorpy-scraper
        echo -e "${GREEN}Container started. View logs with:${NC} docker logs -f shorpy-scraper"
        ;;
    docker-compose)
        echo -e "${GREEN}Running with docker-compose...${NC}"
        docker-compose up -d
        echo -e "${GREEN}Container started. View logs with:${NC} docker-compose logs -f"
        ;;
    status)
        echo -e "${GREEN}Sending status report...${NC}"
        python monitor.py --report
        ;;
    detailed-status)
        echo -e "${GREEN}Sending detailed status report...${NC}"
        python monitor.py --report --detailed
        ;;
    health)
        echo -e "${GREEN}Running health check...${NC}"
        python monitor.py --health-check
        ;;
    cleanup)
        echo -e "${GREEN}Cleaning up temporary files...${NC}"
        python monitor.py --cleanup
        ;;
    test)
        echo -e "${GREEN}Testing Telegram connection...${NC}"
        python test_channel.py
        ;;
    async-test)
        echo -e "${GREEN}Testing asynchronous scraper...${NC}"
        python async_scraper.py
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

# If we're in a virtual environment, deactivate it
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
    echo -e "${GREEN}Deactivated virtual environment${NC}"
fi

exit 0 