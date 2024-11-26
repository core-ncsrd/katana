import logging
from logging import handlers
import pickle
import time
import uuid
import os
import requests
import json

from bson.binary import Binary
from bson.json_util import dumps
from flask import request
from flask_classful import FlaskView, route
import pymongo

from katana.shared_utils.mongoUtils import mongoUtils
from katana.shared_utils.policyUtils import neatUtils, test_policyUtils

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


class PolicyView(FlaskView):
    route_prefix = "/api/"
    req_fields = ["id", "url", "type"]

    def index(self):
        """
        Returns a list of policy management system and their details,
        used by: `katana policy ls`
        """
        policy_data = mongoUtils.index("policy")
        return_data = []
        for item in policy_data:
            return_data.append(
                dict(
                    _id=item["_id"],
                    component_id=item["id"],
                    created_at=item["created_at"],
                    type=item["type"],
                )
            )
        return dumps(return_data)

    def get(self, uuid):
        """
        Returns the details of specific policy management system,
        used by: `katana policy inspect [uuid]`
        """
        data = mongoUtils.get("policy", uuid)
        if data:
            return dumps(data), 200
        else:
            return "Not Found", 404

    def post(self):
        """
        Add a new policy management system. The request must provide the
         system details. used by: `katana policy add -f [file]`
        """
        # Create the object and store it in the object collection
        try:
            if request.json["type"] == "test-policy":
                policy = test_policyUtils.Policy(id=request.json["id"], url=request.json["url"])
            elif request.json["type"] == "neat":
                policy = neatUtils.Policy(id=request.json["id"], url=request.json["url"])
            else:
                return "Error: Not supported Policy system type", 400
        except KeyError:
            return f"Error: Required fields: {self.req_fields}", 400
        new_uuid = str(uuid.uuid4())
        request.json["_id"] = new_uuid
        request.json["created_at"] = time.time()  # unix epoch
        try:
            new_uuid = mongoUtils.add("policy", request.json)
        except pymongo.errors.DuplicateKeyError:
            return (
                "Policy management system with id {0} already exists".format(request.json["id"]),
                400,
            )
        # Store the policy object to the mongo db
        thebytes = pickle.dumps(policy)
        obj_json = {"_id": new_uuid, "id": request.json["id"], "obj": Binary(thebytes)}
        mongoUtils.add("policy_obj", obj_json)
        return new_uuid, 201

    def delete(self, uuid):
        """
        Delete a specific policy management system.
        used by: `katana policy rm [uuid]`
        """
        del_policy = mongoUtils.delete("policy", uuid)
        if del_policy:
            return "Deleted policy management system {}".format(uuid), 200
        else:
            # if uuid is not found, return error
            return "Error: No such policy management system: {}".format(uuid), 404

    def put(self, uuid):
        """
        Update the details of a specific policy engine system.
        used by: `katana policy update [uuid] -f [file]`
        """
        data = request.json
        data["_id"] = uuid
        old_data = mongoUtils.get("policy", uuid)

        if old_data:
            data["created_at"] = old_data["created_at"]
            try:
                for entry in self.req_fields:
                    if data[entry] != old_data[entry]:
                        return "Cannot update field: " + entry, 400
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            else:
                mongoUtils.update("policy", uuid, data)
            return f"Modified {uuid}", 200
        else:
            # Create the object and store it in the object collection
            try:
                if request.json["type"] == "test-policy":
                    policy = test_policyUtils.Policy(id=request.json["id"], url=request.json["url"])
                elif request.json["type"] == "neat":
                    policy = neatUtils.Policy(id=request.json["id"], url=request.json["url"])
                else:
                    return "Error: Not supported Policy system type", 400
            except KeyError:
                return f"Error: Required fields: {self.req_fields}", 400
            new_uuid = uuid
            request.json["_id"] = new_uuid
            request.json["created_at"] = time.time()  # unix epoch
            try:
                new_uuid = mongoUtils.add("policy", request.json)
            except pymongo.errors.DuplicateKeyError:
                return (
                    "Policy management system with id {0} already exists".format(
                        request.json["id"]
                    ),
                    400,
                )
            # Store the policy object to the mongo db
            thebytes = pickle.dumps(policy)
            obj_json = {"_id": new_uuid, "id": request.json["id"], "obj": Binary(thebytes)}
            mongoUtils.add("policy_obj", obj_json)
            return new_uuid, 201

    # NEAT Policy Engine specific Endpoints
    @route("/neat/<slice_id>", methods=["GET"])
    def neat(self, slice_id):
        """
        Send the slice parameters to the neat UE Policy System
        """
        slice_parameters = mongoUtils.get("slice", slice_id)
        if slice_parameters:
            return slice_parameters, 200
        else:
            return f"Slice with id {slice_id} was not found", 404

    # APEX Policy Engine specific Endpoints
    @route("/apex/action", methods=["POST"])
    def apex_action(self):
        """
        Receive feedback from the APEX policy engine
        """
        # Check if APEX is configured in katana
        isapex = os.getenv("APEX", None)
        if not isapex:
            return "APEX Policy Engine is not configured", 400
        apexpolicy = request.json
        logger.info(f"Received new APEX action: {apexpolicy}")
        try:
            # Check the Policy Type
            if apexpolicy["policyType"] == "FailingNS":
                failing_ns_action = apexpolicy["policy"]["action"]
                slice_id = apexpolicy["policy"]["slice_id"]
                ns_id = apexpolicy["policy"]["ns_id"]
                nsd_id = apexpolicy["policy"]["nsd_id"]
                # Notify NEAT if needed
                notify_neat = apexpolicy["policy"]["extra_actions"].get("notify_neat", False)
                if not notify_neat:
                    notify_neat = apexpolicy["policy"]["extra_actions"].get("notify_NEAT", False)
                if notify_neat:
                    neat_list = mongoUtils.find_all("policy", {"type": "neat"})
                    for ineat in neat_list:
                        # Get the NEAT object
                        neat_obj = pickle.loads(mongoUtils.get("policy_obj", ineat["_id"])["obj"])
                        neat_obj.notify(alert_type="FailingNS", slice_id=slice_id, status=True)
                if failing_ns_action == "restart_ns":
                    # Scenario 1
                    restart_ns_message = {
                        "domain": "NFV",
                        "action": "RestartNS",
                        "details": {"ns_id": ns_id, "location": nsd_id, "change_vim": False},
                    }
                    r_url = f"http://katana-nbi:8000/api/slice/{slice_id}/modify"
                    r = requests.post(
                        f"http://katana-nbi:8000/api/slice/{slice_id}/modify",
                        json=json.loads(json.dumps(restart_ns_message)),
                    )
                    return "Restaring the NS", 200
                elif failing_ns_action == "restart_slice":
                    # Scenario 2
                    restart_ns_message = {
                        "domain": "NFV",
                        "action": "RestartNS",
                        "details": {"ns_id": ns_id, "location": nsd_id, "change_vim": True},
                    }
                    r_url = f"http://katana-nbi:8000/api/slice/{slice_id}/modify"
                    r = requests.post(
                        f"http://katana-nbi:8000/api/slice/{slice_id}/modify",
                        json=json.loads(json.dumps(restart_ns_message)),
                    )
                    return "Restaring the NS", 200
                elif failing_ns_action == "stop_slice":
                    # Scenario 3
                    r_url = f"http://katana-nbi:8000/api/slice/{slice_id}"
                    r = requests.delete(r_url)
                    return "Stopping Slice", 200
                else:
                    return f"Action {failing_ns_action} is not supported", 400
            else:
                return f"Policy type {apexpolicy['policyType']} is not supported", 400
        except KeyError as err:
            return f"Key {err} is missing", 400
