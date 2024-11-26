import logging
from logging import handlers
import time
import uuid
import pymongo

from bson.json_util import dumps
from flask.globals import request
from flask_classful import FlaskView

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


class LocationView(FlaskView):
    route_prefix = "/api/"
    req_fields = ["id"]

    def index(self):
        """
        Returns a list of the registered platform locations that will be covered by Katana
        used by `katana location ls`
        """
        location_data = mongoUtils.index("location")
        return dumps(location_data), 200

    def get(self, uuid):
        """
        Returns the details of a specific platform location
        used by: `katana location inspect [uuid]`
        """
        data = mongoUtils.get("location", uuid)
        if data:
            return dumps(data), 200
        else:
            return f"Location {uuid} not found", 404

    def post(self):
        """
        Register a new platform location
        used by: `katana location add -f [file]`
        """
        # Generate a new uuid
        new_uuid = str(uuid.uuid4())
        request.json["_id"] = new_uuid
        request.json["created_at"] = time.time()  # unix epoch
        request.json["vims"] = []
        request.json["functions"] = []
        for ifield in self.req_fields:
            if not request.json.get(ifield, None):
                return f"Field {ifield} is missing"
            else:
                # Lowercase the location
                request.json["id"] = request.json["id"].lower()
        try:
            new_uuid = mongoUtils.add("location", request.json)
        except pymongo.errors.DuplicateKeyError:
            return (f"Location {request.json['id']} is already registered", 400)
        return new_uuid, 201

    def delete(self, uuid):
        """
        Delete a registered platform location
        used by: `katana location rm [uuid]
        """
        del_location = mongoUtils.get("location", uuid)
        if del_location["id"] == "core":
            return "You cannot delete core location", 400
        if del_location:
            if del_location["vims"] or del_location["functions"]:
                return (
                    f"Location {uuid} is in use by another component, cannot update it",
                    400,
                )
            del_location = mongoUtils.delete("location", uuid)
            return f"Deleted location {uuid}", 200
        else:
            return f"Error: No such location {uuid}", 404

    def put(self, uuid):
        """
        Update a registered platform location
        used by: `katana location update [uuid] -f [file]`
        """
        for ifield in self.req_fields:
            if not request.json.get(ifield, None):
                return f"Field {ifield} is missing"
            else:
                # Lowercase the location
                request.json["id"] = request.json["id"].lower()
        data = request.json
        data["_id"] = uuid
        old_data = mongoUtils.get("location", uuid)
        if old_data:
            if old_data["vims"] or old_data["functions"]:
                return (
                    f"Location {data['_id']} is in use by another component, cannot update it",
                    400,
                )
            data["created_at"] = old_data["created_at"]
            data["vims"] = []
            data["functions"] = []
            mongoUtils.update("location", uuid, data)
            return f"Modified location {data['id']}", 200
        else:
            data["created_at"] = time.time()  # unix epoch
            data["vims"] = []
            data["functions"] = []
            new_uuid = mongoUtils.add("location", request.json)
            return new_uuid, 201
