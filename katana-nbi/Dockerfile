FROM python:3.10.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -qq -y \
  build-essential libpq-dev --no-install-recommends \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV INSTALL_PATH /katana-nbi
RUN mkdir -p $INSTALL_PATH

# Set working directory
WORKDIR $INSTALL_PATH

# Copy target JSON files
COPY katana-prometheus/wim_targets.json /targets/wim_targets.json
COPY katana-prometheus/vim_targets.json /targets/vim_targets.json

# Copy application files
COPY katana-nbi/. .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Command to run the application
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--reload", "katana.app:create_app()"]
ENV CURL_CA_BUNDLE=
