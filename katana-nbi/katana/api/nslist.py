# -*- coding: utf-8 -*-
import logging
from logging import handlers
import pickle

from bson.json_util import dumps
from flask_classful import FlaskView
from flask import request

from katana.shared_utils.mongoUtils import mongoUtils
from katana.shared_utils.nfvoUtils import osmUtils

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


class NslistView(FlaskView):
    route_prefix = "/api/"

    def get(self):
        """
        Returns a list with all the onboarded nsds,
        used by: `katana ns ls`
        """

        # Bootstrap the NFVO
        nfvo_obj_list = list(mongoUtils.find_all("nfvo_obj"))
        for infvo in nfvo_obj_list:
            nfvo = pickle.loads(infvo["obj"])
            nfvo.bootstrapNfvo()

        nsd_id = request.args.get("nsd-id", None)
        nfvo_id = request.args.get("nfvo-id", None)
        search_params = {}
        if nsd_id:
            search_params["nsd-id"] = nsd_id
        if nfvo_id:
            search_params["nfvo_id"] = nfvo_id

        # Return the list
        ns_list = mongoUtils.find_all("nsd", search_params)
        return dumps(ns_list), 200
