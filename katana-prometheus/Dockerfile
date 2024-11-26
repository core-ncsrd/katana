FROM prom/prometheus:v2.22.1

RUN mkdir -p /etc/prometheus/rules

COPY katana-prometheus/prometheus.yml /etc/prometheus/prometheus.yml
COPY katana-prometheus/alerts.yml /etc/prometheus/rules/alerts.yml