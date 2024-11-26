import logging
from logging import handlers
import uuid

from bson.json_util import dumps
from flask import request
from flask_classful import FlaskView, route
import urllib3

from katana.shared_utils.kafkaUtils import kafkaUtils
from katana.shared_utils.mongoUtils import mongoUtils
from katana.slice_mapping import slice_mapping

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


class SliceView(FlaskView):
    """
    Returns a list of slices and their details,
    used by: `katana slice ls`
    """

    urllib3.disable_warnings()
    route_prefix = "/api/"

    def index(self):
        """
        Returns a list of slices and their details,
        used by: `katana slice ls`
        """
        slice_data = mongoUtils.index("slice")
        return_data = []
        for islice in slice_data:
            return_data.append(dict(_id=islice["_id"], name=islice["slice_name"], created_at=islice["created_at"], status=islice["status"],))
        return dumps(return_data), 200

    def get(self, uuid):
        """
        Returns the details of specific slice,
        used by: `katana slice inspect [uuid]`
        """
        data = mongoUtils.get("slice", uuid)
        if data:
            return dumps(data), 200
        else:
            return "Not Found", 404

    @route("/<uuid>/time")
    def show_time(self, uuid):
        """
        Returns deployment time of a slice
        """
        islice = mongoUtils.get("slice", uuid)
        if islice:
            return dumps(islice["deployment_time"]), 200
        else:
            return "Not Found", 404

    @route("/<uuid>/modify", methods=["POST"])
    def modify(self, uuid):
        """
        Update the details of a specific slice.
        used by: `katana slice modify -f [file] [uuid]`
        """
        result = mongoUtils.get("slice", uuid)
        if not result:
            return f"Error: No such slice: {uuid}", 404
        # Send the message to katana-mngr
        producer = kafkaUtils.create_producer()
        slice_message = {"action": "update", "slice_id": uuid, "updates": request.json}
        producer.send("slice", value=slice_message)
        return f"Updating {uuid}", 200

    def post(self):
        """
        Add a new slice. The request must provide the slice details.
        used by: `katana slice add -f [file]`
        """
        new_uuid = str(uuid.uuid4())
        request.json["_id"] = new_uuid
        # Get the NEST from the Slice Mapping process
        nest, error_code = slice_mapping.nest_mapping(request.json)

        if error_code:
            return nest, error_code

        # Send the message to katana-mngr
        producer = kafkaUtils.create_producer()
        slice_message = {"action": "add", "message": nest}
        producer.send("slice", value=slice_message)

        return new_uuid, 201

    def delete(self, uuid):
        """
        Delete a specific slice.
        used by: `katana slice rm [uuid]`
        """

        # Check if slice uuid exists
        delete_json = mongoUtils.get("slice", uuid)
        try:
            force = request.args["force"]
        except KeyError:
            force = None
        else:
            force = force if force == "true" else None

        if not delete_json:
            return f"Error: No such slice: {uuid}", 404
        else:
            # Send the message to katana-mngr
            producer = kafkaUtils.create_producer()
            slice_message = {"action": "delete", "message": uuid, "force": force}
            producer.send("slice", value=slice_message)
            return f"Deleting {uuid}", 200

    @route("<uuid>/errors")
    def show_errors(self, uuid):
        """
        Display the runitime errors of a slice
        """
        data = mongoUtils.get("slice", uuid)
        if data:
            runtime_errors = data["runtime_errors"]
            return dumps(runtime_errors), 200
        else:
            return "Slice not found", 404
