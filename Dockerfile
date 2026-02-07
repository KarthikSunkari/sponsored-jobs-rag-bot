# Use Python 3.11 slim image
FROM python:3.11-slim

# Install Chromium and dependencies (works on both ARM64 and AMD64)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Set display port to avoid crash
ENV DISPLAY=:99

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for ChromeDriver cache
RUN mkdir -p /root/.wdm

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV WDM_LOG_LEVEL=0

# Default command (can be overridden)
CMD ["python", "-u", "etl/scrape_jobs.py", "--level", "newgrad", "--max-jobs", "20"]
