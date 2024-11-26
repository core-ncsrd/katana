FROM python:3.7.4-slim

RUN mkdir -p /nfv_mon

WORKDIR /nfv_mon
COPY katana-nfv_mon/. .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

ENV PYTHONPATH=.

CMD [ "python", katana/exporter.py ]