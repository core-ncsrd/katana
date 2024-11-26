import logging
from logging import handlers
import uuid

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

NEST_FIELDS = ("base_slice_descriptor", "service_descriptor", "test_descriptor")
REQ_FIELDS = {"network_DL_throughput", "delay_tolerance"}

SLICE_DES_OBJ = (
    "base_slice_des_id",
    "base_slice_des_ref",
    "delay_tolerance",
    "network_DL_throughput",
    "ue_DL_throughput",
    "network_UL_throughput",
    "ue_UL_throughput",
    "deterministic_communication",
    "group_communication_support",
    "isolation",
    "mtu",
    "mission_critical_support",
    "mmtel_support",
    "nb_iot",
    "number_of_connections",
    "number_of_terminals",
    "positional_support",
    "simultaneous_nsi",
    "nonIP_traffic",
    "device_velocity",
    "terminal_density",
)
SLICE_DES_LIST = ("coverage", "radio_spectrum", "qos")

SERVICE_DES_OBJ = ()
SERVICE_DES_LIST = ("ns_list",)

TEST_DES_OBJ = ("performance_monitoring", "performance_prediction")
TEST_DES_LIST = ("probe_list",)


# Calculate the Required generation
def calc_find_data(gen, location, func):
    """
    Calculate the Required radio service generation (4G or 5G) and return a dictionary
    with all the information
    """
    if gen == 5:
        return {"location": location, "gen": 5, "func": func}
    else:
        return {"location": location, "gen": 4, "func": func}


def nest_mapping(req):
    """
    Function that maps nest to the underlying network functions
    """

    # Store the gst in DB
    mongoUtils.add("gst", req)

    nest = {"_id": req["_id"]}

    # Check if the base_slice_des_ref or the required fields are set
    try:
        base_slice_des_ref = req["base_slice_descriptor"].get("base_slice_des_ref", None)
    except KeyError:
        logger.error("Required field base_slice_descriptor is missing")
        return ("Error: Required field base_slice_descriptor is missing", 400)
    if not base_slice_des_ref:
        for req_key in REQ_FIELDS:
            if req_key not in req["base_slice_descriptor"]:
                logger.error(f"Required field base_slice_descriptor.{req_key} is missing")
                return (
                    f"Error: Required field base_slice_descriptor.{req_key} is missing",
                    400,
                )

    for field in NEST_FIELDS:
        req[field] = req.get(field, None)

    # ****** STEP 1: Slice Descriptor ******
    if not req["base_slice_descriptor"]:
        logger.error("No Base Slice Descriptor given - Exit")
        return "NEST Error: No Base Slice Descriptor given", 400
    req_slice_des = req["base_slice_descriptor"]
    # *** Recreate the NEST ***
    for req_key in SLICE_DES_OBJ:
        req_slice_des[req_key] = req_slice_des.get(req_key, None)
    for req_key in SLICE_DES_LIST:
        req_slice_des[req_key] = req_slice_des.get(req_key, [])

    # *** Check if there are references for slice ***
    if req_slice_des["base_slice_des_ref"]:
        ref_slice = mongoUtils.find("base_slice_des_ref", {"base_slice_des_id": req_slice_des["base_slice_des_ref"]})
        if ref_slice:
            for key, value in req_slice_des.items():
                try:
                    if value is None or value == []:
                        req_slice_des[key] = ref_slice[key]
                except KeyError:
                    continue
        else:
            logger.error("slice_descriptor {} not found".format(req_slice_des["base_slice_des_ref"]))
            return "Error: referenced slice_descriptor not found", 400

    # Replace the None value of the isolation with 0 - No Isolation
    if not req_slice_des["isolation"]:
        req_slice_des["isolation"] = 0

    # Create the shared value
    nest["shared"] = {
        "isolation": req_slice_des["isolation"],
        "simultaneous_nsi": req_slice_des["simultaneous_nsi"],
    }

    # Check that the location in coverage field is registered
    not_supp_loc = []
    supp_loc = []
    for location_id in req_slice_des["coverage"]:
        if not mongoUtils.find("location", {"id": location_id.lower()}):
            not_supp_loc.append(location_id)
            logger.warning(f"Location {location_id} is not registered")
        else:
            supp_loc.append(location_id.lower())

    req_slice_des["not_supported_locations"] = not_supp_loc
    req_slice_des["coverage"] = supp_loc

    # *************************** Start the mapping ***************************
    # Currently supports:
    # 1) If delay_tolerance --> EMBB else --> URLLC
    #    If EMBB --> EPC Placement=@Core. If URLLC --> EPC Placement=@Edge
    # 2) If network throughput > 100 Mbps --> Type=5G
    # *************************************************************************
    functions_list = []

    if req_slice_des["network_DL_throughput"]["guaranteed"] > 100000:
        gen = 5
    else:
        gen = 4

    # *** Calculate the type of the slice (sst) ***
    if req_slice_des["delay_tolerance"]:
        # EMBB
        nest["sst"] = 1
        # Find the registered function for Core Function
        epc = mongoUtils.find("func", calc_find_data(gen, "core", 0))
        if not epc:
            return "Error: Not available Core Network Functions", 400
        # Check if the nest allows shareable functions, if the function is shareable
        if req_slice_des["isolation"] != 1 and req_slice_des["isolation"] != 3 and epc["shared"]["availability"]:
            found_list_key = None
            max_len = epc["shared"].get("max_shared", 0)
            for grouped_nest_key, grouped_nest_list in epc["shared"]["sharing_list"].items():
                if len(grouped_nest_list) < max_len or not max_len:
                    found_list_key = grouped_nest_key
                    grouped_nest_list.append(nest["_id"])
                    sharing_list = mongoUtils.get("sharing_lists", found_list_key)
                    sharing_list["nest_list"].append(nest["_id"])
                    mongoUtils.update("sharing_lists", found_list_key, sharing_list)
                    break
            if not found_list_key:
                found_list_key = str(uuid.uuid4())
                epc["shared"]["sharing_list"][found_list_key] = [nest["_id"]]
                data = {
                    "_id": found_list_key,
                    "nest_list": [nest["_id"]],
                    "nsd_list": {},
                    "ns_list": [],
                }
                mongoUtils.add("sharing_lists", data)
            nest["shared"]["core"] = {epc["_id"]: found_list_key}
        connections = []
        not_supp_loc = []
        for location in req_slice_des["coverage"]:
            enb = mongoUtils.find("func", calc_find_data(gen, location.lower(), 1))
            if not enb:
                not_supp_loc.append(location)
            else:
                # Check if the nest allows shareable functions, if the function is shareable
                if req_slice_des["isolation"] < 2 and enb["shared"]["availability"]:
                    found_list_key = None
                    max_len = enb["shared"].get("max_shared", 0)
                    for grouped_nest_key, grouped_nest_list in enb["shared"]["sharing_list"].items():
                        if len(grouped_nest_list) < max_len or not max_len:
                            found_list_key = grouped_nest_key
                            grouped_nest_list.append(nest["_id"])
                            sharing_list = mongoUtils.get("sharing_lists", found_list_key)
                            sharing_list["nest_list"].append(nest["_id"])
                            mongoUtils.update("sharing_lists", found_list_key, sharing_list)
                            break
                    if not found_list_key:
                        found_list_key = str(uuid.uuid4())
                        enb["shared"]["sharing_list"][found_list_key] = [nest["_id"]]
                        data = {
                            "_id": found_list_key,
                            "nest_list": [nest["_id"]],
                            "nsd_list": {},
                            "ns_list": [],
                        }
                        mongoUtils.add("sharing_lists", data)
                    nest["shared"]["radio"] = nest["shared"].get("radio", {})
                    nest["shared"]["radio"][enb["_id"]] = found_list_key
                connections.append({"core": epc, "radio": enb})
                enb["tenants"].append(nest["_id"])
                mongoUtils.update("func", enb["_id"], enb)
                functions_list.append(enb["_id"])
        if not epc or not connections:
            return "Error: Not available Network Functions", 400
        epc["tenants"].append(nest["_id"])
        mongoUtils.update("func", epc["_id"], epc)
        functions_list.append(epc["_id"])
        for location in not_supp_loc:
            logger.warning(f"Location {location} not supported")
            req_slice_des["coverage"].remove(location)
    else:
        # URLLC
        nest["sst"] = 2
        connections = []
        not_supp_loc = []
        for location in req_slice_des["coverage"]:
            epc = mongoUtils.find("func", calc_find_data(gen, location.lower(), 0))
            enb = mongoUtils.find("func", calc_find_data(gen, location.lower(), 1))
            if not epc or not enb:
                not_supp_loc.append(location)
            else:
                # Check if the nest allows shareable functions, if the function is shareable
                # For the Core function
                if req_slice_des["isolation"] != 1 and req_slice_des["isolation"] != 3 and epc["shared"]["availability"]:
                    found_list_key = None
                    max_len = epc["shared"].get("max_shared", 0)
                    for grouped_nest_key, grouped_nest_list in epc["shared"]["sharing_list"].items():
                        if len(grouped_nest_list) < max_len or not max_len:
                            found_list_key = grouped_nest_key
                            grouped_nest_list.append(nest["_id"])
                            sharing_list = mongoUtils.get("sharing_lists", found_list_key)
                            sharing_list["nest_list"].append(nest["_id"])
                            mongoUtils.update("sharing_lists", found_list_key, sharing_list)
                            break
                    if not found_list_key:
                        found_list_key = str(uuid.uuid4())
                        epc["shared"]["sharing_list"][found_list_key] = [nest["_id"]]
                        data = {
                            "_id": found_list_key,
                            "nest_list": [nest["_id"]],
                            "nsd_list": {},
                            "ns_list": [],
                        }
                        mongoUtils.add("sharing_lists", data)
                    nest["shared"]["core"] = nest["shared"].get("core", {})
                    nest["shared"]["core"][epc["_id"]] = found_list_key
                # For the RAN function
                if req_slice_des["isolation"] < 2 and enb["shared"]["availability"]:
                    found_list_key = None
                    max_len = enb["shared"].get("max_shared", 0)
                    for grouped_nest_key, grouped_nest_list in enb["shared"]["sharing_list"].items():
                        if len(grouped_nest_list) < max_len or not max_len:
                            found_list_key = grouped_nest_key
                            grouped_nest_list.append(nest["_id"])
                            sharing_list = mongoUtils.get("sharing_lists", found_list_key)
                            sharing_list["nest_list"].append(nest["_id"])
                            mongoUtils.update("sharing_lists", found_list_key, sharing_list)
                            break
                    if not found_list_key:
                        found_list_key = str(uuid.uuid4())
                        enb["shared"]["sharing_list"][found_list_key] = [nest["_id"]]
                        data = {
                            "_id": found_list_key,
                            "nest_list": [nest["_id"]],
                            "nsd_list": {},
                            "ns_list": [],
                        }
                        mongoUtils.add("sharing_lists", data)
                    nest["shared"]["radio"] = nest["shared"].get("radio", {})
                    nest["shared"]["radio"][enb["_id"]] = found_list_key
                connections.append({"core": epc, "radio": enb})
                epc["tenants"].append(nest["_id"])
                enb["tenants"].append(nest["_id"])
                mongoUtils.update("func", enb["_id"], enb)
                mongoUtils.update("func", epc["_id"], epc)
                functions_list.extend([epc["_id"], enb["_id"]])
        if not connections:
            return "Error: Not available Network Functions", 400
        for location in not_supp_loc:
            logger.warning(f"Location {location} not supported")
            req_slice_des["coverage"].remove(location)

    nest["connections"] = connections
    nest["functions"] = functions_list

    # Values to be copied to NEST
    KEYS_TO_BE_COPIED = (
        "network_DL_throughput",
        "ue_DL_throughput",
        "network_UL_throughput",
        "ue_UL_throughput",
        "group_communication_support",
        "mtu",
        "number_of_terminals",
        "positional_support",
        "radio_spectrum",
        "device_velocity",
        "terminal_density",
        "coverage",
    )
    for key in KEYS_TO_BE_COPIED:
        nest[key] = req_slice_des[key]

    # Add slice_name to NEST based on the base_slice_des id
    nest["slice_name"] = req_slice_des["base_slice_des_id"]

    # ****** STEP 2: Service Descriptor ******
    if req["service_descriptor"]:
        req_service_des = req["service_descriptor"]
        # *** Recreate the NEST ***
        for req_key in SERVICE_DES_OBJ:
            req_service_des[req_key] = req_service_des.get(req_key, None)
        for req_key in SERVICE_DES_LIST:
            req_service_des[req_key] = req_service_des.get(req_key, [])
        # Create the NS field on Nest
        nest["ns_list"] = req_service_des["ns_list"]

        # # Replace Placement with location in each NS
        # for ns in nest["ns_list"]:
        #     ns["placement"] = (
        #         lambda x: {"location": ["Core"]} if not x else
        #         {"location": req_slice_des["coverage"]})(ns["placement"])

    # ****** STEP 3: Test Descriptor ******
    if req["test_descriptor"]:
        req_test_des = req["test_descriptor"]
        # *** Recreate the NEST ***
        for req_key in TEST_DES_OBJ:
            req_test_des[req_key] = req_test_des.get(req_key, None)
        for req_key in TEST_DES_LIST:
            req_test_des[req_key] = req_test_des.get(req_key, [])
        # Create the Probe field on Nest
        nest["probe_list"] = req_test_des["probe_list"]

    if not mongoUtils.find("base_slice_des_ref", {"base_slice_des_id": req["base_slice_descriptor"]["base_slice_des_id"]},) and req["base_slice_descriptor"]["base_slice_des_id"]:
        new_uuid = str(uuid.uuid4())
        req["base_slice_descriptor"]["_id"] = new_uuid
        mongoUtils.add("base_slice_des_ref", req["base_slice_descriptor"])
    return nest, 0
