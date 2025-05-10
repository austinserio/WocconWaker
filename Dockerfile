# Base image
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# Set working directory
WORKDIR /app

# Install system dependencies including supervisord
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create supervisord configuration directory
RUN mkdir -p /etc/supervisor/conf.d

# Create supervisord configuration file
RUN echo "[supervisord]\nnodaemon=true\n\n[program:woccon]\ncommand=uvicorn woccon_app:app --host 0.0.0.0 --port 8000\nautostart=true\nautorestart=true\nstdout_logfile=/var/log/woccon.log\nstderr_logfile=/var/log/woccon.err" > /etc/supervisor/conf.d/woccon.conf

# Expose the port
EXPOSE 8000

# Run the server using supervisord
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]