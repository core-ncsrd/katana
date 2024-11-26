# -*- coding: utf-8 -*-
import logging
from logging import handlers
import uuid

from bson.json_util import dumps
from flask import request
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


class Base_slice_desView(FlaskView):
    route_prefix = "/api/"

    def index(self):
        """
        Returns a list of Slice Descriptors and their details,
        used by: `katana slice_des ls`
        """
        slice_des_data = mongoUtils.index("base_slice_des_ref")
        return_data = []
        for islicedes in slice_des_data:
            return_data.append(dict(_id=islicedes["_id"], base_slice_des_id=islicedes["base_slice_des_id"]))
        return dumps(return_data), 200

    def post(self):
        """
        Add a new base slice descriptor. The request must provide the base
        slice descriptor details. Used by: `katana slice_des add -f [file]`
        """
        new_uuid = str(uuid.uuid4())
        data = request.json
        data["_id"] = new_uuid
        return str(mongoUtils.add("base_slice_des_ref", data)), 201

    def get(self, uuid):
        """
        Returns the details of specific Slice Descriptor,
        used by: `katana slice_des inspect [uuid]`
        """
        data = mongoUtils.get("base_slice_des_ref", uuid)
        if data:
            return dumps(data), 200
        else:
            return "Not Found", 404

    def put(self, uuid):
        """
        Add or update a new base slice descriptor.
        The request must provide the service details.
        used by: `katana slice_des update -f [file]`
        """
        data = request.json
        data["_id"] = uuid
        old_data = mongoUtils.get("base_slice_des_ref", uuid)

        if old_data:
            mongoUtils.update("base_slice_des_ref", uuid, data)
            return f"Modified {uuid}", 200
        else:
            new_uuid = uuid
            data = request.json
            data["_id"] = new_uuid
            return str(mongoUtils.add("base_slice_des_ref", data)), 201

    def delete(self, uuid):
        """
        Delete a specific Slice Descriptor.
        used by: `katana slice_des rm [uuid]`
        """
        result = mongoUtils.delete("base_slice_des_ref", uuid)
        if result:
            return f"Deleted Slice Descriptor {uuid}", 200
        else:
            # if uuid is not found, return error
            return f"Error: No such Slice Descriptor: {uuid}", 404
