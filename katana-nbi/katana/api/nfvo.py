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
from requests import ConnectTimeout, ConnectionError  # type: ignore

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


class NFVOView(FlaskView):
    route_prefix = "/api/"
    req_fields = ["id", "nfvousername", "nfvopassword", "nfvoip", "tenantname"]

    def index(self):
        """
        Returns a list of nfvo and their details,
        used by: `katana nfvo ls`
        """
        nfvo_data = mongoUtils.index("nfvo")
        return_data = []
        for infvo in nfvo_data:
            return_data.append(dict(_id=infvo["_id"], nfvo_id=infvo["id"], created_at=infvo["created_at"], type=infvo["type"],))
        return dumps(return_data), 200

    # @route('/all/') #/nfvo/all
    def all(self):
        """
        Same with index(self) above, but returns all nfvo details
        """
        return dumps(mongoUtils.index("nfvo")), 200

    def get(self, uuid):
        """
        Returns the details of specific nfvo,
        used by: `katana nfvo inspect [uuid]`
        """
        data = mongoUtils.get("nfvo", uuid)
        if data:
            return dumps(data), 200
        else:
            return "Not Found", 404

    def post(self):
        """
        Add a new nfvo. The request must provide the nfvo details.
        used by: `katana nfvo add -f [file]`
        """
        new_uuid = str(uuid.uuid4())
        request.json["_id"] = new_uuid
        request.json["created_at"] = time.time()  # unix epoch
        request.json["tenants"] = {}

        if request.json["type"] == "OSM":
            # Create the NFVO object
            try:
                osm_username = request.json["nfvousername"]
                osm_password = request.json["nfvopassword"]
                osm_ip = request.json["nfvoip"]
                osm_project_name = request.json["tenantname"]
                nfvo_id = request.json["id"]
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            else:
                osm = osmUtils.Osm(nfvo_id, osm_ip, osm_username, osm_password, osm_project_name)
            try:
                osm.getToken()
            except ConnectTimeout as e:
                logger.exception(f"Connection Timeout: {e}")
                response = dumps({"error": "Unable to connect to NFVO"})
                return (response, 400)
            except ConnectionError as e:
                logger.exception(f"Connection Error: {e}")
                response = dumps({"error": "Unable to connect to NFVO"})
                return (response, 400)
            else:
                # Store the osm object to the mongo db
                thebytes = pickle.dumps(osm)
                obj_json = {"_id": new_uuid, "id": request.json["id"], "obj": Binary(thebytes)}
                try:
                    new_uuid = mongoUtils.add("nfvo", request.json)
                except pymongo.errors.DuplicateKeyError:
                    return f"NFVO with id {nfvo_id} already exists", 400
                mongoUtils.add("nfvo_obj", obj_json)
                # Get information regarding VNFDs and NSDs
                osm.bootstrapNfvo()
                return new_uuid, 201
        else:
            response = dumps({"error": "This type nfvo is not supported"})
            return response, 400

    def delete(self, uuid):
        """
        Delete a specific nfvo.
        used by: `katana nfvo rm [uuid]`
        """
        del_nfvo = mongoUtils.get("nfvo", uuid)
        if del_nfvo:
            if del_nfvo["tenants"]:
                return f"Cannot delete nfvo {uuid} - In use", 400
            mongoUtils.delete("nfvo_obj", uuid)
            mongoUtils.delete_all("nsd", {"nfvo_id": del_nfvo["id"]})
            mongoUtils.delete_all("vnfd", {"nfvoid": del_nfvo["id"]})
            mongoUtils.delete("nfvo", uuid)
            return f"Deleted NFVO {uuid}", 200
        else:
            # if uuid is not found, return error
            return f"Error: No such nfvo: {uuid}", 404

    def put(self, uuid):
        """
        Update the details of a specific nfvo.
        used by: `katana nfvo update -f [file] [uuid]`
        """
        data = request.json
        data["_id"] = uuid
        old_data = mongoUtils.get("nfvo", uuid)

        if old_data:
            data["created_at"] = old_data["created_at"]
            data["tenants"] = old_data["tenants"]
            try:
                for entry in self.req_fields:
                    if data[entry] != old_data[entry]:
                        return "Cannot update field: " + entry, 400
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            else:
                mongoUtils.update("nfvo", uuid, data)
            return f"Modified {uuid}", 200
        else:
            new_uuid = uuid
            data = request.json
            data["_id"] = new_uuid
            data["created_at"] = time.time()  # unix epoch
            data["tenants"] = {}

            if request.json["type"] == "OSM":
                # Create the NFVO object
                try:
                    osm_username = request.json["nfvousername"]
                    osm_password = request.json["nfvopassword"]
                    osm_ip = request.json["nfvoip"]
                    osm_project_name = request.json["tenantname"]
                    nfvo_id = request.json["id"]
                except KeyError:
                    return f"Error: Required fields: {self.req_fields}", 400
                else:
                    osm = osmUtils.Osm(nfvo_id, osm_ip, osm_username, osm_password, osm_project_name)
                try:
                    osm.getToken()
                except ConnectTimeout as e:
                    logger.exception("Connection Timeout: {}".format(e))
                    response = dumps({"error": "Unable to connect to NFVO"})
                    return (response, 400)
                except ConnectionError as e:
                    logger.exception("Connection Error: {}".format(e))
                    response = dumps({"error": "Unable to connect to NFVO"})
                    return (response, 400)
                else:
                    # Store the osm object to the mongo db
                    thebytes = pickle.dumps(osm)
                    obj_json = {"_id": new_uuid, "id": data["id"], "obj": Binary(thebytes)}
                    try:
                        new_uuid = mongoUtils.add("nfvo", data)
                    except pymongo.errors.DuplicateKeyError:
                        return f"NFVO with id {nfvo_id} already exists", 400
                    mongoUtils.add("nfvo_obj", obj_json)
                    # Get information regarding VNFDs and NSDs
                    osm.bootstrapNfvo()
            else:
                response = dumps({"error": "This type nfvo is not supported"})
                return response, 400
            return new_uuid, 201
