import logging
import os
from logging import handlers
from flask import request
from flask_classful import FlaskView
from time import sleep

from katana.shared_utils.mongoUtils import mongoUtils
from katana.shared_utils.sliceUtils.sliceUtils import check_runtime_errors
from katana.shared_utils.kafkaUtils.kafkaUtils import create_producer

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


class AlertView(FlaskView):
    route_prefix = "/api/"

    def post(self):
        """
        Get a new alert
        """
        alert_message = request.json
        # Check the alert type
        for ialert in alert_message["alerts"]:
            if ialert["labels"]["alertname"] == "NSFailing":
                ns_id = ialert["labels"]["ns_name"].split("__")[1].replace("_", "-")
                location = ialert["labels"]["ns_name"].split("__")[2]
                slice_id = ialert["labels"]["slice_id"]
                logger.warning(
                    f"Failing Network Service {ns_id} in {location} for slice {slice_id}"
                )
                # Update the NEST
                nest = mongoUtils.get("slice", slice_id)
                try:
                    nest["ns_inst_info"][ns_id][location]["status"] = "Error"
                except KeyError:
                    pass
                # Add the error to the runtime errors
                ns_errors = nest["runtime_errors"].get("ns", [])
                ns_errors.append(ns_id)
                nest["runtime_errors"]["ns"] = ns_errors
                check_runtime_errors(nest)
                # Notify APEX
                isapex = os.getenv("APEX", None)
                if isapex:
                    apex_message = {
                        "name": "SMAlert",
                        "nameSpace": "sm.alert.manager.events",
                        "version": "0.0.1",
                        "source": "SMAlertManager",
                        "target": "APEX",
                        "sliceId": slice_id,
                        "alertType": "FailingNS",
                        "alertMessage": {"NS_ID": ns_id, "NSD_ID": location, "status": "down"},
                    }
                    sleep(10)
                    apex_producer = create_producer()
                    logger.info(f"Sending alert to APEX {apex_message}")
                    apex_producer.send("apex-in-0", value=apex_message)
        return "Alert received", 200
