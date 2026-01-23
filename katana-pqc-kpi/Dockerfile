FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY katana-pqc-kpi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY katana-pqc-kpi/ .

# Expose the port
EXPOSE 8080 5005

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "katana/pqc_server.py"]
