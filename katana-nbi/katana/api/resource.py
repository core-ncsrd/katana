# -*- coding: utf-8 -*-
import logging
from logging import handlers
import pickle
from threading import Thread

from bson.json_util import dumps
from flask_classful import FlaskView, route

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


def get_vims(filter_data=None):
    """
    Return the list of available VIMs
    """
    vims = []
    for vim in mongoUtils.find_all("vim", data=filter_data):
        vims.append(
            {
                "name": vim["name"],
                "id": vim["id"],
                "location": vim["location"],
                "type": vim["type"],
                "tenants": vim["tenants"],
                "resources": vim["resources"],
            }
        )
    return vims


def get_func(filter_data={}):
    """
    Return the list of available Network Functions
    """
    filter_data["type"] = 1
    data = mongoUtils.find_all("func", data=filter_data)
    functions = []
    for iserv in data:
        functions.append(
            dict(
                DB_ID=iserv["_id"],
                gen=(lambda x: "4G" if x == 4 else "5G")(iserv["gen"]),
                functionality=(lambda x: "Core" if x == 0 else "Radio")(iserv["func"]),
                pnf_list=iserv.get("pnf_list", []),
                function_id=iserv["id"],
                location=iserv["location"],
                tenants=iserv["tenants"],
                shared=iserv["shared"],
                created_at=iserv["created_at"],
            )
        )
    return functions


def vim_update():
    """
    Gets the resources of the stored VIMs
    """
    for vim in mongoUtils.find_all("vim"):
        if vim["type"] == "openstack":
            vim_obj = pickle.loads(mongoUtils.get("vim_obj", vim["_id"])["obj"])
            resources = vim_obj.get_resources()
            vim["resources"] = resources
            mongoUtils.update("vim", vim["_id"], vim)
        else:
            resources = "N/A"


class ResourcesView(FlaskView):
    route_prefix = "/api/"

    def index(self):
        """
        Returns the available resources on platform,
        used by: `katana resource ls`
        """
        # Get VIMs
        vims = get_vims()
        # Get Functions
        functions = get_func()
        # Get locations
        locations = mongoUtils.find_all("location")
        resources = {"VIMs": vims, "Functions": functions, "Locations": locations}
        return dumps(resources), 200

    def get(self, uuid):
        """
        Returns the available resources on platform,
        used by: `katana resource location <location>`
        """
        location_id = uuid.lower()
        # Check if the location exists
        if not mongoUtils.find("location", {"id": location_id}):
            return f"Location {uuid} not found", 404
        # Get VIMs
        filter_data = {"location": location_id}
        vims = get_vims(filter_data)
        # Get Functions
        functions = get_func(filter_data)
        resources = {"VIMs": vims, "Functions": functions}
        return dumps(resources), 200

    @route("/update", methods=["GET", "POST"])
    def update(self):
        """
        Update the resource database for the stored VIMs
        """
        thread = Thread(target=vim_update)
        thread.start()
        return "Updating resource database", 200
