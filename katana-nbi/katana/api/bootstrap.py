# -*- coding: utf-8 -*-
import logging
import requests
import json
from logging import handlers

from flask import request
from flask_classful import FlaskView

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


class BootstrapView(FlaskView):
    route_prefix = "/api/"

    def post(self):
        """
        Add a new configuration file to the SM.
        used by: `katana bootstrap -f [file]`
        """
        data_fields = ["vim", "nfvo", "ems", "wim", "function"]
        data = request.json
        for field in data_fields:
            component_list = data.get(field, [])
            for component_data in component_list:
                url = f"http://localhost:8000/api/{field}"
                r = None
                try:
                    r = requests.post(url, json=component_data, timeout=30)
                    r.raise_for_status()
                    logger.info(r.text)
                except requests.exceptions.HTTPError as errh:
                    print("Http Error:", errh)
                    logger.info(r.text)
                except requests.exceptions.ConnectionError as errc:
                    print("Error Connecting:", errc)
                except requests.exceptions.Timeout as errt:
                    print("Timeout Error:", errt)
                except requests.exceptions.RequestException as err:
                    print("Error:", err)
        return "Succesfully configured SM", 201
