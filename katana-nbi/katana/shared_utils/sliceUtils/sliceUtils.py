import logging
import pickle
import os
from logging import handlers

from katana.shared_utils.mongoUtils import mongoUtils
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


def check_runtime_errors(nest):
    """
    Function that checks about slice runtime errors and updates the slice status
    """

    slice_id = nest["_id"]
    if nest["runtime_errors"]:
        nest_status = "runtime_error"
    else:
        nest_status = "Running"
        # Notify NEAT
        isapex = os.getenv("APEX", None)
        if isapex:
            neat_list = mongoUtils.find_all("policy", {"type": "neat"})
            for ineat in neat_list:
                # Get the NEAT object
                neat_obj = pickle.loads(mongoUtils.get("policy_obj", ineat["_id"])["obj"])
                neat_obj.notify(alert_type="FailingNS", slice_id=slice_id, status=False)
    nest["status"] = nest_status
    mongoUtils.update("slice", slice_id, nest)
    # Update monitoring status
    if nest["slice_monitoring"]:
        mon_producer = create_producer()
        mon_producer.send(
            "nfv_mon",
            value={
                "action": "katana_mon",
                "slice_info": {"slice_id": nest["_id"], "status": nest_status},
            },
        )
