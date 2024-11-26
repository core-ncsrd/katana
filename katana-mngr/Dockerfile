FROM python:3.7.4-slim

RUN apt-get update && apt-get install -qq -y \
  build-essential libpq-dev --no-install-recommends

ENV INSTALL_PATH /katana-mngr
ENV PYTHONPATH ${INSTALL_PATH}
RUN mkdir -p $INSTALL_PATH

WORKDIR $INSTALL_PATH

COPY katana-grafana/templates /katana-grafana/templates

COPY katana-mngr/. .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD python3 katana/katana-mngr.py