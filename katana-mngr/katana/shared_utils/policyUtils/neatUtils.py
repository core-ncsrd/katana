import requests
import json
import logging
from logging import handlers


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


class Policy:
    """
    Class implementing the communication API with Policy System
    """

    def __init__(self, url, id):
        """
        Initialize an object of the class
        """
        self.url = url

    def send_nest(self, data):
        """
        Send the nest parameters
        """
        api_prefix = ""
        url = self.url + api_prefix
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        r = None
        try:
            r = requests.post(url, json=json.loads(json.dumps(data)), timeout=360, headers=headers)
            logger.info(r.json())
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            logger.exception("Http Error:", errh)
        except requests.exceptions.ConnectionError as errc:
            logger.exception("Error Connecting:", errc)
        except requests.exceptions.Timeout as errt:
            logger.exception("Timeout Error:", errt)
        except requests.exceptions.RequestException as err:
            logger.exception("Error:", err)

    def notify(self, alert_type, slice_id, status):
        """
        Notify NEAT policy engine
        """
        neat_message = {
            "slice_id": slice_id,
            "type": alert_type,
            "value": status,
            "ttl": -1,
        }
        neat_url = self.url + "/event"
        neat_headers = {"Content-type": "Application/JSON"}
        r = requests.put(neat_url, json=json.loads(json.dumps(neat_message)), headers=neat_headers)
        logger.info(f"Notifying NEAT, message: {neat_message}")
