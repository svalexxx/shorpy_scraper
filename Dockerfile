FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p /app/data/scraped_posts /app/data/temp_images

# Set environment variables
ENV PYTHONPATH=/app
ENV TZ=Asia/Nicosia

# Run the scraper
CMD ["python", "main.py", "--schedule", "--silent", "--report-to", "29909617"] 