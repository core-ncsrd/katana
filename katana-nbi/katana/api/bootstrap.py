# -*- coding: utf-8 -*-
import logging
from logging import handlers

from flask import jsonify, request
from flask_classful import FlaskView

from katana.shared_utils.bootstrapUtils import BootstrapError, reconcile_manifest
from katana.shared_utils.mongoUtils import mongoUtils

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

    def index(self):
        """Return the latest bootstrap result without credential material."""
        status = mongoUtils.get("bootstrap_status", "latest")
        if not status:
            return jsonify({"status": "never_run"}), 200
        status = dict(status)
        status.pop("_id", None)
        return jsonify(status), 200

    def post(self):
        """
        Add a new configuration file to the SM.
        used by: `katana bootstrap -f [file]`
        """
        try:
            result = reconcile_manifest(request.get_json(silent=True) or {})
        except BootstrapError as exc:
            logger.error("Bootstrap failed: %s", exc)
            return jsonify({"status": "failed", "error": str(exc), "results": exc.results}), exc.status_code
        return jsonify(result), 200
