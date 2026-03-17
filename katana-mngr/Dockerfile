FROM python:3.10.12-slim

# Install system build dependencies required for C-extensions (like pymongo)
RUN apt-get update && apt-get install -qq -y \
  build-essential libpq-dev --no-install-recommends \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV INSTALL_PATH /katana-mngr
ENV PYTHONPATH ${INSTALL_PATH}
RUN mkdir -p $INSTALL_PATH

WORKDIR $INSTALL_PATH

# Copy templates and source code
COPY katana-grafana/templates /katana-grafana/templates
COPY katana-mngr/. .

# Upgrade pip and install requirements without using old cached binaries
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "katana/katana-mngr.py"]