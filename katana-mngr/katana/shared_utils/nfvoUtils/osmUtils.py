import logging
import logging.handlers
import uuid
import json

import pymongo
import requests

from katana.shared_utils.mongoUtils import mongoUtils

# Logging Parameters
logger = logging.getLogger(__name__)
file_handler = logging.handlers.RotatingFileHandler("katana.log", maxBytes=10000, backupCount=5)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(stream_formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


class Osm:
    """
    Class implementing the communication API with OSM
    """

    def __init__(self, nfvo_id, ip, username, password, project_id="admin", timeout=5):
        """
        Initialize an object of the class
        """
        self.ip = ip
        self.username = username
        self.password = password
        self.project_id = project_id
        self.token = ""
        self.timeout = timeout
        self.nfvo_id = nfvo_id

    def getToken(self):
        """
        Returns a valid Token for OSM
        """
        headers = {
            "Content-Type": "application/yaml",
            "Accept": "application/json",
        }

        data = (
            "{username: '"
            + self.username
            + "', password: '"
            + self.password
            + "', project_id: '"
            + self.project_id
            + "'}"
        )
        url = f"https://{self.ip}/osm/admin/v1/tokens"
        response = requests.post(
            url, headers=headers, data=data, verify=False, timeout=self.timeout
        )
        try:
            response_data = response.json()
            logger.debug("Received token response: %s", json.dumps(response_data, indent=2))
            self.token = response_data["id"]
        except ValueError:
            logger.error("Failed to decode JSON response while fetching token: %s", response.text)
            self.token = ""
        return self.token

    def addVim(self, vimName, vimPassword, vimType, vimUrl, vimUser, secGroup):
        """
        Registers a VIM to the OSM VIM account list
        Returns VIM id
        """
        osm_url = f"https://{self.ip}/osm/admin/v1/vim_accounts"
        data = '{{ name: "{0}", vim_password: "{1}", vim_tenant_name: "{2}",\
            vim_type: "{3}", vim_url: "{4}", vim_user: "{5}" , config: {6}}}'.format(
            vimName, vimPassword, vimName, vimType, vimUrl, vimUser, secGroup
        )
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.post(osm_url, headers=headers, data=data, verify=False)
            if response.status_code != 401:
                try:
                    response_data = response.json()
                    logger.debug("Received VIM response: %s", json.dumps(response_data, indent=2))
                    vim_id = response_data["id"]
                    break
                except ValueError:
                    logger.error("Failed to decode JSON response while adding VIM: %s", response.text)
                    return None
            else:
                self.getToken()
        return vim_id

    def instantiateNs(self, nsName, nsdId, vimAccountId):
        """
        Instantiates a NS on the OSM
        Returns the NS ID
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/ns_instances_content"

        data = "{{ nsName: {0}, nsdId: {1}, vimAccountId: {2} }}".format(
            nsName, nsdId, vimAccountId
        )
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.post(osm_url, headers=headers, data=data, verify=False)
            if response.status_code != 401:
                try:
                    response_data = response.json()
                    logger.debug("Received NS instantiation response: %s", json.dumps(response_data, indent=2))
                    nsId = response_data
                    break
                except ValueError:
                    logger.error("Failed to decode JSON response while instantiating NS: %s", response.text)
                    return None
            else:
                self.getToken()
        return nsId.get("id", None) if nsId else None

    def getNsr(self, nsId):
        """
        Returns the NSR for a given NS ID
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/ns_instances/{nsId}"
        # Get the NSR from NS ID in json format
        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(osm_url, headers=headers, verify=False)
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    logger.debug("Received NSR response: %s", json.dumps(response_data, indent=2))
                    nsr = response_data
                    break
                except ValueError:
                    logger.error("Failed to decode JSON response while getting NSR: %s", response.text)
                    return {}
            elif response.status_code == 401:
                self.getToken()
            else:
                return {}
        return nsr

    def getVnfrId(self, nsr):
        """
        Retrieve list of VNFrIDS from NSR
        """
        try:
            vnfrId_list = nsr["constituent-vnfr-ref"]
            return vnfrId_list
        except KeyError:
            logger.error("Failed to retrieve VNFR IDs from NSR: %s", json.dumps(nsr, indent=2))
            return []

    def getVnfr(self, vnfrId):
        """
        Retrieve VNFR from VNFRID
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/vnf_instances/{vnfrId}"
        # Get the VNFR from VNF ID in json format
        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(osm_url, headers=headers, verify=False)
            if response.status_code != 401:
                try:
                    response_data = response.json()
                    logger.debug("Received VNFR response: %s", json.dumps(response_data, indent=2))
                    vnfr = response_data
                    break
                except ValueError:
                    logger.error("Failed to decode JSON response while getting VNFR: %s", response.text)
                    return None
            else:
                self.getToken()
        return vnfr

    def getIPs(self, vnfr):
        """
        Retrieve a list of IPs from a VNFR
        """
        try:
            vnf_name = vnfr["vnfd-ref"]
            mgmt_ip = vnfr["ip-address"]
            vdu_ips = []
            vm_list = []
            for i in vnfr["vdur"]:
                for ip in i["interfaces"]:
                    vdu_ips.append(ip["ip-address"])
                vm_list.append(i["name"])
            vnf_info = {
                "vnf_name": vnf_name,
                "mgmt_ip": mgmt_ip,
                "vdu_ips": vdu_ips,
                "vm_list": vm_list,
            }
            return vnf_info
        except KeyError as e:
            logger.error("Failed to retrieve IPs from VNFR: %s", str(e))
            return {}

    def deleteNs(self, nsId):
        """
        Terminates and deletes the given ns
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/ns_instances_content/{nsId}"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.delete(osm_url, headers=headers, verify=False)
            if response.status_code != 401:
                return
            else:
                self.getToken()

    def deleteVim(self, vimID):
        """
        Deletes the tenant account from the osm
        """
        osm_url = f"https://{self.ip}/osm/admin/v1/vim_accounts/{vimID}"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/yaml",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.delete(osm_url, headers=headers, verify=False)
            if response.status_code != 401:
                return
            else:
                self.getToken()

    def bootstrapNfvo(self):
        """
        Reads info from NSDs/VNFDs in the NFVO and stores them in mongodb
        """
        self.readVnfd()
        self.readNsd()

    def readVnfd(self):
        """
        Reads and returns required information from nsd/vnfd
        """
        url = f"https://{self.ip}/osm/vnfpkgm/v1/vnf_packages/"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(url, headers=headers, verify=False)
            if response.status_code != 401:
                try:
                    response_data = response.json()
                    logger.debug("Received VNFD response: %s", json.dumps(response_data, indent=2))
                    osm_vnfd_list = response_data
                    for osm_vnfd in osm_vnfd_list:
                        if all(key in osm_vnfd for key in ("id", "_id", "mgmt-interface", "vdu")):
                            new_vnfd = {
                                "vnfd-id": osm_vnfd["_id"],
                                "name": osm_vnfd["id"],
                                "flavor": {"memory-mb": 0, "vcpu-count": 0, "storage-gb": 0},
                                "mgmt": osm_vnfd["mgmt-interface"]["cp"],
                                "nfvo_id": self.nfvo_id,
                                "_id": str(uuid.uuid4()),
                            }
                            instances = 0
                            for vdu in osm_vnfd["vdu"]:
                                if "vm-flavor" in vdu.keys():
                                    for key in new_vnfd["flavor"]:
                                        new_vnfd["flavor"][key] += int(vdu["vm-flavor"][key])
                                    instances += 1
                            new_vnfd["flavor"]["instances"] = instances
                            try:
                                mongoUtils.add("vnfd", new_vnfd)
                            except pymongo.errors.DuplicateKeyError:
                                continue
                    break
                except ValueError:
                    logger.error("Failed to decode JSON response while reading VNFD: %s", response.text)
                    break
            else:
                self.getToken()

    def readNsd(self):
        """
        Reads and returns required information from nsd/vnfd
        """
        url = f"https://{self.ip}/osm/nsd/v1/ns_descriptors"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(url, headers=headers, verify=False)
            if response.status_code != 401:
                try:
                    response_data = response.json()
                    logger.debug("Received NSD response: %s", json.dumps(response_data, indent=2))
                    osm_nsd_list = response_data
                    for osm_nsd in osm_nsd_list:
                        new_nsd = {
                            "nsd-id": osm_nsd["_id"],
                            "nsd-name": osm_nsd["id"],
                            "vnfd_list": [],
                            "flavor": {
                                "memory-mb": 0,
                                "vcpu-count": 0,
                                "storage-gb": 0,
                                "instances": 0,
                            },
                            "nfvo_id": self.nfvo_id,
                            "_id": str(uuid.uuid4()),
                        }
                        for osm_vnfd in osm_nsd.get("constituent-vnfd", []):
                            data = {"name": osm_vnfd["vnfd-id-ref"]}
                            reg_vnfd = mongoUtils.find("vnfd", data)
                            if reg_vnfd:
                                new_nsd["vnfd_list"].append(reg_vnfd["name"])
                                for key in new_nsd["flavor"]:
                                    new_nsd["flavor"][key] += reg_vnfd["flavor"][key]
                        try:
                            mongoUtils.add("nsd", new_nsd)
                        except pymongo.errors.DuplicateKeyError:
                            continue
                    break
                except ValueError:
                    logger.error("Failed to decode JSON response while reading NSD: %s", response.text)
                    break
            else:
                self.getToken()

    def checkNsLife(self, nsId):
        """
        Checks if an NS is running
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/ns_instances/{nsId}"
        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(osm_url, headers=headers, verify=False)
            if response.status_code != 401:
                try:
                    response_data = response.json()
                    logger.debug("Received NS life check response: %s", json.dumps(response_data, indent=2))
                    nsr = response_data
                    if nsr.get("operational-status") == "terminated":
                        self.deleteNs(nsId)
                        return True
                    return False
                except ValueError:
                    logger.error("Failed to decode JSON response while checking NS life: %s", response.text)
                    return True
            else:
                self.getToken()
        return False
