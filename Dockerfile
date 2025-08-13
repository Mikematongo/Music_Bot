# Use official Python slim image
FROM python:3.12-slim

# Install ffmpeg and other dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg curl git && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable for UTF-8
ENV PYTHONUTF8=1

# Start command
CMD ["python", "music_bot.py"]
