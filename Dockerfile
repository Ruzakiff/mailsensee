FROM python:3.11-slim

# Install necessary packages
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/user_data /app/user_data/tokens

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/user_data

# Expose the port
EXPOSE 5000

# Command to run the application
CMD ["python", "app.py"]