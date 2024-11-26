import json
import logging
from logging import handlers

import requests

from katana.shared_utils.kafkaUtils import kafkaUtils

# Logging Parameters
logger = logging.getLogger(__name__)
file_handler = handlers.RotatingFileHandler("katana.log", maxBytes=10000, backupCount=5)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(stream_formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


class Wim:
    """
    Class implementing the communication API with WIM
    """

    def __init__(self, url):
        """
        Initialize an object of the class
        """
        self.url = url

    def create_slice(self, wsd):
        """
        Create the transport network slice
        """
        wim_message = {"action": "create", "data": wsd}

        # Create the kafka producer
        bootstrap_servers = [f"{self.url}:9092"]
        producer = kafkaUtils.create_producer(bootstrap_servers=bootstrap_servers)
        producer.send("wan-slice", value=wim_message)
        logger.info("Sent WAN Slice Creation request to WIM")

    def del_slice(self, slice_id):
        """
        Delete the transport network slice
        """
        wim_message = {"action": "terminate", "data": slice_id}
        bootstrap_servers = [f"{self.url}:9092"]
        producer = kafkaUtils.create_producer(bootstrap_servers=bootstrap_servers)
        producer.send("wan-slice", value=wim_message)
        logger.info("Sent WAN Slice Termination request to WIM")
