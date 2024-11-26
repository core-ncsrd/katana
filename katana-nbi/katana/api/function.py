# -*- coding: utf-8 -*-
import logging
from logging import handlers
import time
import uuid

from bson.json_util import dumps
from flask import request
from flask_classful import FlaskView
import pymongo

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


class FunctionView(FlaskView):
    route_prefix = "/api/"
    req_fields = ["id", "gen", "func", "shared", "type", "location"]

    def index(self):
        """
        Returns a list of supported functions and their details,
        used by: `katana function ls`
        """
        data = mongoUtils.index("func")
        return_data = []
        for iserv in data:
            return_data.append(
                dict(
                    _id=iserv["_id"],
                    gen=(lambda x: "4G" if x == 4 else "5G")(iserv["gen"]),
                    func=(lambda x: "Core" if x == 0 else "Radio")(iserv["func"]),
                    type=(lambda x: "Virtual" if x == 0 else "Physical")(iserv["type"]),
                    func_id=iserv["id"],
                    loc=iserv["location"],
                    created_at=iserv["created_at"],
                )
            )
        return dumps(return_data), 200

    def get(self, uuid):
        """
        Returns the details of specific function,
        used by: `katana function inspect [uuid]`
        """
        return dumps(mongoUtils.get("func", uuid)), 200

    def post(self):
        """
        Add a new supported function.
        The request must provide the network function details.
        used by: `katana func add -f [file]`
        """
        new_uuid = str(uuid.uuid4())
        data = request.json
        data["_id"] = new_uuid
        data["created_at"] = time.time()  # unix epoch
        data["tenants"] = []
        data["shared"]["sharing_list"] = {}

        for field in self.req_fields:
            try:
                _ = data[field]
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400

        # Check that the Function location is registered
        location_id = request.json["location"].lower()
        request.json["location"] = location_id
        location = mongoUtils.find("location", {"id": location_id})
        if not location:
            return f"Location {location_id} is not registered. Please add the location first", 400
        location["functions"].append(data["id"])

        try:
            new_uuid = mongoUtils.add("func", data)
        except pymongo.errors.DuplicateKeyError:
            return f"Network Function with id {data['id']} already exists", 400
        mongoUtils.update("location", location["_id"], location)
        return new_uuid, 201

    def delete(self, uuid):
        """
        Delete a specific network function.
        used by: `katana function rm [uuid]`
        """
        result = mongoUtils.get("func", uuid)
        if result:
            if len(result["tenants"]) > 0:
                return f"Error: Function is used by slices {result['tenants']}"
            mongoUtils.delete("func", uuid)
            # Update the location removing the Function
            location = mongoUtils.find("location", {"id": result["location"].lower()})
            if location:
                location["functions"].remove(result["id"])
                mongoUtils.update("location", location["_id"], location)
            return f"Deleted Network Function {uuid}", 200
        else:
            # if uuid is not found, return error
            return f"Error: No such Network Function: {uuid}", 404

    def put(self, uuid):
        """
        Add or update a new supported network function.
        The request must provide the service details.
        used by: `katana function update -f [file]`
        """
        data = request.json
        data["_id"] = uuid
        old_data = mongoUtils.get("func", uuid)

        if old_data:
            data["created_at"] = old_data["created_at"]
            data["tenants"] = []
            data["shared"]["sharing_list"] = {}
            if len(old_data["tenants"]) > 0:
                return f"Error: Func is used by slices {old_data['tenants']}"
            mongoUtils.update("func", uuid, data)
            return f"Modified {uuid}", 200
        else:
            new_uuid = uuid
            data = request.json
            data["_id"] = new_uuid
            data["created_at"] = time.time()  # unix epoch
            data["tenants"] = []
            data["shared"]["sharing_list"] = {}

            for field in self.req_fields:
                try:
                    _ = data[field]
                except KeyError:
                    return f"Error: Required fields: {self.req_fields}", 400

            # Check that the VIM location is registered
            location_id = request.json["location"].lower()
            request.json["location"] = location_id
            location = mongoUtils.find("location", {"id": location_id})
            if not location:
                return (
                    f"Location {location_id} is not registered. Please add the location first",
                    400,
                )
            location["functions"].append(data["id"])

            try:
                new_uuid = mongoUtils.add("func", data)
            except pymongo.errors.DuplicateKeyError:
                return f"Function with id {data['id']} already exists", 400
            mongoUtils.update("location", location["_id"], location)
            return new_uuid, 201
