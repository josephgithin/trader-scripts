# Use Python 3.10
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install required system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY config.py .
COPY exchange_monitor.py .
COPY config.json .

# Set terminal and environment variables for smooth updates
ENV PYTHONUNBUFFERED=1
ENV TERM=xterm-256color
ENV COLUMNS=120
ENV LINES=140

# Run the application
CMD ["python", "exchange_monitor.py"]

