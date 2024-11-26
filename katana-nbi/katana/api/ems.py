# -*- coding: utf-8 -*-
import logging
from logging import handlers
import pickle
import time
import uuid

from bson.binary import Binary
from bson.json_util import dumps
from flask import request
from flask_classful import FlaskView
import pymongo

from katana.shared_utils.emsUtils import amar_emsUtils, test_emsUtils, open5gs_emsUtils
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


class EmsView(FlaskView):
    route_prefix = "/api/"
    req_fields = ["url", "id", "type"]

    def index(self):
        """
        Returns a list of EMS and their details,
        used by: `katana ems ls`
        """
        ems_data = mongoUtils.index("ems")
        return_data = []
        for iems in ems_data:
            return_data.append(
                dict(
                    _id=iems["_id"],
                    ems_id=iems["id"],
                    ems_type=iems["type"],
                    created_at=iems["created_at"],
                )
            )
        return dumps(return_data), 200

    # @route('/all/') #/ems/all
    def all(self):
        """
        Same with index(self) above, but returns all EMS details
        """
        return dumps(mongoUtils.index("ems")), 200

    def get(self, uuid):
        """
        Returns the details of specific EMS,
        used by: `katana ems inspect [uuid]`
        """
        data = mongoUtils.get("ems", uuid)
        if data:
            return dumps(data), 200
        else:
            return "Not Found", 404

    def post(self):
        """
        Add a new EMS. The request must provide the ems details.
        used by: `katana ems add -f [file]`
        """
        # TODO: Test connectivity with the EMS
        new_uuid = str(uuid.uuid4())
        # Create the object and store it in the object collection
        try:
            ems_id = request.json["id"]
            if request.json["type"] == "amarisoft-ems":
                ems = amar_emsUtils.Ems(request.json["url"])
            elif request.json["type"] == "test-ems":
                ems = test_emsUtils.Ems(request.json["url"])
            elif request.json["type"] == "open5gs-ems":
                ems = open5gs_emsUtils.Ems(request.json["url"])
            else:
                return "Error: Not supported EMS type", 400
        except KeyError:
            return f"Error: Required fields: {self.req_fields}", 400
        thebytes = pickle.dumps(ems)
        obj_json = {"_id": new_uuid, "id": request.json["id"], "obj": Binary(thebytes)}
        request.json["_id"] = new_uuid
        request.json["created_at"] = time.time()  # unix epoch
        try:
            new_uuid = mongoUtils.add("ems", request.json)
        except pymongo.errors.DuplicateKeyError:
            return f"EMS with id {ems_id} already exists", 400
        mongoUtils.add("ems_obj", obj_json)
        return new_uuid, 201

    def delete(self, uuid):
        """
        Delete a specific EMS.
        used by: `katana ems rm [uuid]`
        """
        mongoUtils.delete("ems_obj", uuid)
        result = mongoUtils.delete("ems", uuid)
        if result:
            return "Deleted EMS {}".format(uuid), 200
        else:
            # if uuid is not found, return error
            return "Error: No such EMS: {}".format(uuid), 404

    def put(self, uuid):
        """
        Update the details of a specific EMS.
        used by: `katana ems update -f [file] [uuid]`
        """
        data = request.json
        data["_id"] = uuid
        old_data = mongoUtils.get("ems", uuid)

        if old_data:
            data["created_at"] = old_data["created_at"]
            try:
                for entry in self.req_fields:
                    if data[entry] != old_data[entry]:
                        return "Cannot update field: " + entry, 400
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            else:
                mongoUtils.update("ems", uuid, data)
            return f"Modified {uuid}", 200
        else:
            new_uuid = uuid
            data = request.json
            data["_id"] = new_uuid
            data["created_at"] = time.time()  # unix epoch
            new_uuid = str(uuid.uuid4())
            # Create the object and store it in the object collection
            try:
                ems_id = request.json["id"]
                if request.json["type"] == "amarisoft-ems":
                    ems = amar_emsUtils.Ems(request.json["url"])
                elif request.json["type"] == "test-ems":
                    ems = test_emsUtils.Ems(request.json["url"])
                elif request.json["type"] == "open5gs-ems":
                    ems = open5gs_emsUtils.Ems(request.json["url"])
                else:
                    return "Error: Not supported EMS type", 400
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            thebytes = pickle.dumps(ems)
            obj_json = {"_id": new_uuid, "id": data["id"], "obj": Binary(thebytes)}
            try:
                new_uuid = mongoUtils.add("ems", data), 201
            except pymongo.errors.DuplicateKeyError:
                return f"EMS with id {ems_id} already exists", 400
            mongoUtils.add("ems_obj", obj_json)
            return new_uuid, 201
