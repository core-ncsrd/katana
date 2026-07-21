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
from katana.shared_utils.infrastructureUtils import InfrastructureError
from katana.shared_utils.bootstrapUtils import BootstrapError, _ensure_vim, public_record
from katana.shared_utils.vimUtils import opennebulaUtils
from katana.shared_utils.vimUtils import openstackUtils

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


class VimView(FlaskView):
    route_prefix = "/api/"
    req_fields = ["id", "auth_url", "username", "password", "admin_project_name", "location"]

    def index(self):
        """
        Returns a list of vims and their details,
        used by: `katana vim ls`
        """
        nfvo_id = request.args.get("nfvo_id")
        vim_data = mongoUtils.index("vim")
        return_data = []
        for ivim in vim_data:
            links = list(mongoUtils.find_all("nfvo_vim_links", {"vim_id": ivim["id"]}))
            nfvo_ids = sorted(link["nfvo_id"] for link in links)
            if nfvo_id and nfvo_id not in nfvo_ids:
                continue
            return_data.append(
                dict(
                    _id=ivim["_id"],
                    vim_id=ivim["id"],
                    name=ivim.get("name", ivim["id"]),
                    location=ivim.get("location"),
                    nfvo_ids=nfvo_ids,
                    created_at=ivim["created_at"],
                    type=ivim["type"],
                )
            )
        return dumps(return_data), 200

    # @route('/all/') #/vim/all
    def all(self):
        """
        Same with index(self) above, but returns all vim details
        """
        return dumps([public_record(item) for item in mongoUtils.index("vim")]), 200

    def get(self, uuid):
        """
        Returns the details of specific vim,
        used by: `katana vim inspect [uuid]`
        """
        data = mongoUtils.get("vim", uuid)
        if data:
            data = public_record(data)
            data["nfvo_links"] = [
                public_record(link)
                for link in mongoUtils.find_all("nfvo_vim_links", {"vim_id": data["id"]})
            ]
            return dumps(data), 200
        else:
            return "Not Found", 404

    def post(self):
        """
        Add a new vim. The request must provide the vim details.
        used by: `katana vim add -f [file]`
        """
        data = request.get_json(silent=True) or {}
        credentials = data.get("credentials")
        if credentials is None:
            credentials = {
                "auth": {
                    "auth_url": data.get("auth_url"),
                    "username": data.get("username"),
                    "password": data.get("password"),
                    "project_name": data.get("admin_project_name"),
                }
            }
        try:
            record, action, _ = _ensure_vim(
                {
                    "id": data["id"],
                    "name": data.get("name", data["id"]),
                    "type": data["type"],
                    "location": data["location"],
                    "cloud": data.get("cloud"),
                    "credentials": credentials,
                    "verify": data.get("verify", True),
                    "description": data.get("description", ""),
                }
            )
        except (KeyError, InfrastructureError):
            return f"Error: Required fields: {self.req_fields}", 400
        except BootstrapError as exc:
            return str(exc), exc.status_code
        return record["_id"], 201 if action == "created" else 200

    def delete(self, uuid):
        """
        Delete a specific vim.
        used by: `katana vim rm [uuid]`
        """
        vim = mongoUtils.get("vim", uuid)
        if vim:
            if mongoUtils.find("nfvo_vim_links", {"vim_id": vim["id"]}):
                return f"Cannot delete VIM {uuid} - linked by Time-0 bootstrap", 400
            if vim["tenants"]:
                return "Cannot delete vim {} - In use".format(uuid), 400
            mongoUtils.delete("vim_obj", uuid)
            mongoUtils.delete("vim", uuid)
            # Update the location removing the VIM
            location = mongoUtils.find("location", {"id": vim["location"].lower()})
            if location:
                location["vims"].remove(vim["id"])
                mongoUtils.update("location", location["_id"], location)
            return "Deleted VIM {}".format(uuid), 200
        else:
            # if uuid is not found, return error
            return "Error: No such vim: {}".format(uuid), 404

    def put(self, uuid):
        """
        Update the details of a specific vim.
        used by: `katana vim update -f [file] [uuid]`
        """
        data = request.json
        new_uuid = uuid
        data["_id"] = uuid
        old_data = mongoUtils.get("vim", uuid)

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
                mongoUtils.update("vim", uuid, data)
            return f"Modified {uuid}", 200
        else:
            request.json["_id"] = new_uuid
            request.json["created_at"] = time.time()  # unix epoch
            request.json["tenants"] = {}

            try:
                username = request.json["username"]
                password = request.json["password"]
                auth_url = request.json["auth_url"]
                project_name = request.json["admin_project_name"]
                location_id = request.json["location"].lower()
                request.json["location"] = location_id
                vim_id = request.json["id"]
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400

            # Check that the VIM location is registered
            location = mongoUtils.find("location", {"id": location_id})
            if not location:
                return (
                    f"Location {location_id} is not registered. Please add the location first",
                    400,
                )
            location["vims"].append(vim_id)
            # Type of OpenStack
            if request.json["type"] == "openstack":
                try:
                    new_vim = openstackUtils.Openstack(
                        uuid=new_uuid,
                        auth_url=auth_url,
                        project_name=project_name,
                        username=username,
                        password=password,
                    )
                    if new_vim.auth_error:
                        raise (AttributeError)
                except AttributeError:
                    return "Error: VIM Error", 400
                else:
                    request.json["resources"] = new_vim.get_resources()
                    thebytes = pickle.dumps(new_vim)
                    obj_json = {"_id": new_uuid, "id": request.json["id"], "obj": Binary(thebytes)}
                    try:
                        vim_monitoring = request.json["infrastructure_monitoring"]
                    except KeyError:
                        pass
                    else:
                        with open("/targets/vim_targets.json", mode="r") as prom_file:
                            prom = json.load(prom_file)
                            prom.append({"targets": [vim_monitoring], "labels": {}})
                        with open("/targets/vim_targets.json", mode="w") as prom_file:
                            json.dump(prom, prom_file)
            # Type of OpenNebula
            elif request.json["type"] == "opennebula":
                try:
                    new_vim = opennebulaUtils.Opennebula(
                        uuid=new_uuid,
                        auth_url=auth_url,
                        project_name=project_name,
                        username=username,
                        password=password,
                    )
                except AttributeError:
                    return "Error: VIM Error", 400
                else:
                    request.json["resources"] = {"N/A": "N/A"}
                    thebytes = pickle.dumps(new_vim)
                    obj_json = {"_id": new_uuid, "id": request.json["id"], "obj": Binary(thebytes)}
            else:
                response = dumps({"error": "This type VIM is not supported"})
                return response, 400
            try:
                new_uuid = mongoUtils.add("vim", request.json)
            except pymongo.errors.DuplicateKeyError:
                return f"VIM with id {vim_id} already exists", 400
            mongoUtils.add("vim_obj", obj_json)
            if location:
                mongoUtils.update("location", location["_id"], location)
            return new_uuid, 201
