#!/usr/bin/env python3

"""
Katana NFV Prometheus exporter
Read the collected NFV metrics and expose them to Prometheus
"""

import logging
import threading
from time import sleep
import requests
import json
import os

from katana.utils.kafkaUtils.kafkaUtils import create_consumer, create_topic
from katana.utils.threadingUtis.threadingUtils import MonThread
from katana.utils.mongoUtils import mongoUtils
from prometheus_client import start_http_server, Gauge

# Create the logger
logger = logging.getLogger(__name__)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_handler.setFormatter(stream_formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)


def mon_start(ns_list, ns_status, ns_slice_id):
    """
    Starts the monitoring of new network services
    """
    logger.info("Starting Network Function Status monitoring")
    for ns_id, ns in ns_list.items():
        for key, value in ns.items():
            location = key.replace("-", "_")
            ns_monitoring_id = ns_id.replace("-", "_")
            metric_name = "ns__" + ns_monitoring_id + "__" + location
            ns_status.labels(ns_slice_id, metric_name).set(1)
            new_thread = MonThread(value, ns_status, metric_name, ns_slice_id)
            new_thread.name = metric_name
            new_thread.start()


def mon_stop(ns_list):
    """
    Stops the monitoring os new network services
    """
    logger.info("Stoping Network Function Status monitoring")
    for ns_id, ns in ns_list.items():
        for key, value in ns.items():
            location = key.replace("-", "_")
            ns_monitoring_id = ns_id.replace("-", "_")
            metric_name = "ns__" + ns_monitoring_id + "__" + location
            # Get the thread
            for ithread in threading.enumerate():
                if ithread.name != metric_name:
                    continue
                ithread.stop()


def katana_mon(metric, n_slices, slice_info, increment):
    """
    Updates the slice monitoring status
    """
    if slice_info["status"] == "running" or slice_info["status"] == "Running":
        metric.labels(slice_info["slice_id"]).set(0)
        if increment:
            n_slices.inc()
    elif slice_info["status"] == "placement":
        metric.labels(slice_info["slice_id"]).set(1)
    elif slice_info["status"] == "provisioning":
        metric.labels(slice_info["slice_id"]).set(2)
    elif slice_info["status"] == "activation":
        metric.labels(slice_info["slice_id"]).set(3)
    elif slice_info["status"] == "terminating":
        metric.labels(slice_info["slice_id"]).set(10)
    elif slice_info["status"] == "error" or slice_info["status"] == "runtime_error":
        metric.labels(slice_info["slice_id"]).set(11)
    elif slice_info["status"] == "deleted":
        metric.labels(slice_info["slice_id"]).set(12)
        n_slices.dec()


def start_exporter():
    """
    Starts the NFV Monitoring. Creates the Kafka consumer
    """

    # Add the Grafana new Home Dashboard
    with open("katana/dashboards/katana.json", mode="r") as home_dash_file:
        home_dash = json.load(home_dash_file)
        # Use the Grafana API in order to create the new home dashboard
        grafana_url = "http://katana-grafana:3000/api/dashboards/db"
        headers = {"accept": "application/json", "content-type": "application/json"}
        grafana_user = os.getenv("GF_SECURITY_ADMIN_USER", "admin")
        grafana_passwd = os.getenv("GF_SECURITY_ADMIN_PASSWORD", "admin")
        r = requests.post(
            url=grafana_url,
            headers=headers,
            auth=(grafana_user, grafana_passwd),
            data=json.dumps(home_dash),
        )

    # Set the default dashboard to the new katana home dashboard
    grafana_url = "http://katana-grafana:3000/api/org/preferences"
    preferences = {"theme": "", "homeDashboardId": 1, "timezone": "cet"}
    r = requests.put(
        url=grafana_url,
        headers=headers,
        auth=(grafana_user, grafana_passwd),
        data=json.dumps(preferences),
    )

    # Create the Katana Home Monitoring metric
    katana_home = Gauge("katana_status", "Katana Slice Status", ["slice_id"])
    total_slices = Gauge("total_slices", "Number of running slices")

    # Create the prometheus ns status metric
    ns_status = Gauge("ns_status", "Network Service Status", ["slice_id", "ns_name"])

    # Create the Kafka topic
    create_topic("nfv_mon")

    # Create the Kafka consumer
    consumer = create_consumer("nfv_mon")

    for message in consumer:
        if message.value["action"] == "create":
            ns_list = message.value["ns_list"]
            ns_slice_id = message.value["slice_id"]
            mon_start(ns_list, ns_status, ns_slice_id)
        elif message.value["action"] == "delete":
            ns_list = message.value["ns_list"]
            mon_stop(ns_list)
        elif message.value["action"] == "katana_mon":
            increment = message.value.get("increment", False)
            katana_mon(katana_home, total_slices, message.value["slice_info"], increment)
        elif message.value["action"] == "ns_stop":
            ns_id = message.value["ns_id"]
            location = message.value["ns_location"]
            ns_monitoring_id = ns_id.replace("-", "_")
            ns_slice_id = message.value["slice_id"]
            metric_name = "ns__" + ns_monitoring_id + "__" + location
            # Stop the thread
            for ithread in threading.enumerate():
                if ithread.name != metric_name:
                    continue
                ithread.stop()
                sleep(5)
            # Change the status of the NS to admin_stop
            ns_status.labels(ns_slice_id, metric_name).set(5)


if __name__ == "__main__":
    start_http_server(8002)
    start_exporter()
