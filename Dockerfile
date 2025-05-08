FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variable for server mode
ENV WOCCON_MODE=server

# Expose the port
EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "woccon_app:app", "--host", "0.0.0.0", "--port", "8000"]