# -*- coding: utf-8 -*-
import logging
from logging import handlers
import pickle
import time
import uuid
import json

from bson.binary import Binary
from bson.json_util import dumps
from flask import request
from flask_classful import FlaskView
import pymongo

from katana.shared_utils.mongoUtils import mongoUtils
from katana.shared_utils.wimUtils import odl_wimUtils, test_wimUtils

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


class WimView(FlaskView):
    route_prefix = "/api/"
    req_fields = ["id", "url", "type"]

    def index(self):
        """
        Returns a list of wims and their details,
        used by: `katana wim ls`
        """
        wim_data = mongoUtils.index("wim")
        return_data = []
        for iwim in wim_data:
            return_data.append(
                dict(
                    _id=iwim["_id"],
                    wim_id=iwim["id"],
                    wim_type=iwim["type"],
                    created_at=iwim["created_at"],
                )
            )
        return dumps(return_data), 200

    # @route('/all/') #/wim/all
    def all(self):
        """
        Same with index(self) above, but returns all wim details
        """
        return dumps(mongoUtils.index("wim")), 200

    def get(self, uuid):
        """
        Returns the details of specific wim,
        used by: `katana wim inspect [uuid]`
        """
        data = mongoUtils.get("wim", uuid)
        if data:
            return dumps(data), 200
        else:
            return "Not Found", 404

    def post(self):
        """
        Add a new wim. The request must provide the wim details.
        used by: `katana wim add -f [file]`
        """
        # TODO: Test connectivity with the WIM
        new_uuid = str(uuid.uuid4())
        # Create the object and store it in the object collection
        try:
            wim_id = request.json["id"]
            if request.json["type"] == "odl-wim":
                wim = odl_wimUtils.Wim(request.json["url"])
            elif request.json["type"] == "test-wim":
                wim = test_wimUtils.Wim(request.json["url"])
            else:
                return "Error: Not supported WIM type", 400
        except KeyError:
            return f"Error: Required fields: {self.req_fields}", 400
        thebytes = pickle.dumps(wim)
        obj_json = {"_id": new_uuid, "id": request.json["id"], "obj": Binary(thebytes)}
        request.json["_id"] = new_uuid
        request.json["created_at"] = time.time()  # unix epoch
        request.json["slices"] = {}
        try:
            new_uuid = mongoUtils.add("wim", request.json)
        except pymongo.errors.DuplicateKeyError:
            return f"WIM with id {wim_id} already exists", 400
        try:
            monitoring_url = request.json["monitoring-url"]
        except KeyError:
            pass
        else:
            with open("/targets/wim_targets.json", mode="r") as prom_file:
                prom = json.load(prom_file)
                prom.append({"targets": [monitoring_url], "labels": {"wim_id": wim_id}})
            with open("/targets/wim_targets.json", mode="w") as prom_file:
                json.dump(prom, prom_file)
        mongoUtils.add("wim_obj", obj_json)
        return new_uuid, 201

    def delete(self, uuid):
        """
        Delete a specific wim.
        used by: `katana wim rm [uuid]`
        """
        wim = mongoUtils.get("wim", uuid)
        if wim:
            if wim["slices"]:
                return "Cannot delete wim {} - In use".format(uuid), 400
            mongoUtils.delete("wim_obj", uuid)
            mongoUtils.delete("wim", uuid)
            try:
                monitoring_url = wim["monitoring-url"]
            except KeyError:
                pass
            else:
                try:
                    with open("/targets/wim_targets.json", mode="r") as prom_file:
                        prom = json.load(prom_file)
                        prom.remove({"targets": [monitoring_url], "labels": {"wim_id": wim["id"]}})
                    with open("/targets/wim_targets.json", mode="w") as prom_file:
                        json.dump(prom, prom_file)
                except ValueError:
                    pass
            return "Deleted WIM {}".format(uuid), 200
        else:
            # if uuid is not found, return error
            return "Error: No such wim: {}".format(uuid), 404

    def put(self, uuid):
        """
        Update the details of a specific wim.
        used by: `katana wim update -f [file] [uuid]`
        """
        data = request.json
        data["_id"] = uuid
        old_data = mongoUtils.get("wim", uuid)

        if old_data:
            data["created_at"] = old_data["created_at"]
            data["slices"] = old_data["slices"]
            try:
                for entry in self.req_fields:
                    if data[entry] != old_data[entry]:
                        return "Cannot update field: " + entry, 400
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            else:
                mongoUtils.update("wim", uuid, data)
            return f"Modified {uuid}", 200
        else:
            new_uuid = uuid
            data = request.json
            data["_id"] = new_uuid
            data["created_at"] = time.time()  # unix epoch
            try:
                wim_id = request.json["id"]
                if request.json["type"] == "odl-wim":
                    wim = odl_wimUtils.Wim(request.json["url"])
                elif request.json["type"] == "test-wim":
                    wim = test_wimUtils.Wim(request.json["url"])
                else:
                    return "Error: Not supported WIM type", 400
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            thebytes = pickle.dumps(wim)
            obj_json = {"_id": new_uuid, "id": data["id"], "obj": Binary(thebytes)}
            data["slices"] = {}
            try:
                new_uuid = mongoUtils.add("wim", data)
            except pymongo.errors.DuplicateKeyError:
                return f"WIM with id {wim_id} already exists", 400
            try:
                monitoring_url = request.json["monitoring-url"]
            except KeyError:
                pass
            else:
                with open("/targets/wim_targets.json", mode="r") as prom_file:
                    prom = json.load(prom_file)
                    prom.append({"targets": [monitoring_url], "labels": {"wim_id": wim_id}})
                with open("/targets/wim_targets.json", mode="w") as prom_file:
                    json.dump(prom, prom_file)
            mongoUtils.add("wim_obj", obj_json)
            return new_uuid, 201
