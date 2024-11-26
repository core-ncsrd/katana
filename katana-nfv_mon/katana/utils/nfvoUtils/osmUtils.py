import logging
import logging.handlers
import uuid

import pymongo
import requests

from katana.utils.mongoUtils import mongoUtils

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
        url = f"https://{self.ip}:9999/osm/admin/v1/tokens"
        response = requests.post(
            url, headers=headers, data=data, verify=False, timeout=self.timeout
        )
        self.token = response.json()["id"]
        # return token id
        return self.token

    def addVim(self, vimName, vimPassword, vimType, vimUrl, vimUser, secGroup):
        """
        Registers a VIM to the OSM VIM account list
        Returns VIM id
        """
        osm_url = f"https://{self.ip}:9999/osm/admin/v1/vim_accounts"
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
                vim_id = response.json()["id"]
                break
            else:
                self.getToken()
        return vim_id

    def instantiateNs(self, nsName, nsdId, vimAccountId):
        """
        Instantiates a NS on the OSM
        Returns the NS ID
        """
        osm_url = f"https://{self.ip}:9999/osm/nslcm/v1/ns_instances_content"

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
                nsId = response.json()
                break
            else:
                self.getToken()
        return nsId["id"]

    def getNsr(self, nsId):
        """
        Returns the NSR for a given NS ID
        """
        osm_url = f"https://{self.ip}:9999/osm/nslcm/v1/ns_instances/{nsId}"
        # Get the NSR from NS ID in json format
        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(osm_url, headers=headers, verify=False)
            if response.status_code == 200:
                nsr = response.json()
                break
            elif response.status_code == 401:
                self.getToken()
            else:
                return {}
        return nsr

    def getVnfrId(self, nsr):
        """
        Retrieve list of VNFrIDS from NSR
        """
        vnfrId_list = nsr["constituent-vnfr-ref"]
        return vnfrId_list

    def getVnfr(self, vnfrId):
        """
        Retrieve VNFR from VNFRID
        """
        osm_url = f"https://{self.ip}:9999/osm/nslcm/v1/vnf_instances/{vnfrId}"
        # Get the VNFR from VNF ID in json format
        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(osm_url, headers=headers, verify=False)
            if response.status_code != 401:
                vnfr = response.json()
                break
            else:
                self.getToken()
        return vnfr

    def getIPs(self, vnfr):
        """
        Retrieve a list of IPs from a VNFR
        """
        vnf_name = vnfr["vnfd-ref"]
        mgmt_ip = vnfr["ip-address"]
        vdu_ips = []
        for i in vnfr["vdur"]:
            for ip in i["interfaces"]:
                vdu_ips.append(ip["ip-address"])
        vnf_info = {"vnf_name": vnf_name, "mgmt_ip": mgmt_ip, "vdu_ips": vdu_ips}
        return vnf_info

    def deleteNs(self, nsId):
        """
        Terminates and deletes the given ns
        """
        osm_url = f"https://{self.ip}:9999/osm/nslcm/v1/ns_instances_content/" + nsId
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
        osm_url = f"https://{self.ip}:9999/osm/admin/v1/vim_accounts/{vimID}"
        headers = {
            "Content-Type": "application/yaml",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
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
        url = f"https://{self.ip}:9999/osm/vnfpkgm/v1/vnf_packages/"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(url, headers=headers, verify=False)
            if response.status_code != 401:
                osm_vnfd_list = response.json()
                new_vnfd = {}
                for osm_vnfd in osm_vnfd_list:
                    if all(key in osm_vnfd for key in ("id", "_id", "mgmt-interface", "vdu")):
                        new_vnfd["vnfd-id"] = osm_vnfd["_id"]
                        new_vnfd["name"] = osm_vnfd["id"]
                        new_vnfd["flavor"] = {"memory-mb": 0, "vcpu-count": 0, "storage-gb": 0}
                        instances = 0
                        for vdu in osm_vnfd["vdu"]:
                            if "vm-flavor" in vdu.keys():
                                for key in new_vnfd["flavor"]:
                                    new_vnfd["flavor"][key] += int(vdu["vm-flavor"][key])
                                instances += 1
                        new_vnfd["flavor"]["instances"] = instances
                        new_vnfd["mgmt"] = osm_vnfd["mgmt-interface"]["cp"]
                        new_vnfd["nfvo_id"] = self.nfvo_id
                        new_vnfd["_id"] = str(uuid.uuid4())
                        try:
                            mongoUtils.add("vnfd", new_vnfd)
                        except pymongo.errors.DuplicateKeyError:
                            continue
                        new_vnfd = {}
                break
            else:
                self.getToken()

    def readNsd(self):
        """
        Reads and returns required information from nsd/vnfd
        """
        url = f"https://{self.ip}:9999/osm/nsd/v1/ns_descriptors"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(url, headers=headers, verify=False)
            if response.status_code != 401:
                osm_nsd_list = response.json()
                new_nsd = {}
                for osm_nsd in osm_nsd_list:
                    new_nsd["nsd-id"] = osm_nsd["_id"]
                    new_nsd["nsd-name"] = osm_nsd["id"]
                    new_nsd["vnfd_list"] = []
                    new_nsd["flavor"] = {
                        "memory-mb": 0,
                        "vcpu-count": 0,
                        "storage-gb": 0,
                        "instances": 0,
                    }
                    for osm_vnfd in osm_nsd["constituent-vnfd"]:
                        data = {"name": osm_vnfd["vnfd-id-ref"]}
                        reg_vnfd = mongoUtils.find("vnfd", data)
                        if not reg_vnfd:
                            logger.warning("There is a vnfd missing from the NFVO repository")
                        else:
                            new_nsd["vnfd_list"].append(reg_vnfd["name"])
                            for key in new_nsd["flavor"]:
                                new_nsd["flavor"][key] += reg_vnfd["flavor"][key]
                    new_nsd["nfvo_id"] = self.nfvo_id
                    new_nsd["_id"] = str(uuid.uuid4())
                    try:
                        mongoUtils.add("nsd", new_nsd)
                    except pymongo.errors.DuplicateKeyError:
                        continue
                    new_nsd = {}
                break
            else:
                self.getToken()

    def checkNsLife(self, nsId):
        """
        Checks if an NS is running
        """
        osm_url = f"https://{self.ip}:9999/osm/nslcm/v1/ns_instances/{nsId}"
        # Get the NSR from NS ID in json format
        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(osm_url, headers=headers, verify=False)
            if response.status_code != 401:
                status = response.status_code
                break
            else:
                self.getToken()
        return True if status == 404 else False
