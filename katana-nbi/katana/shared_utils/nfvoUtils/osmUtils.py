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
        self.token = response.json()["_id"]
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
                nsId = response.json()
                break
            else:
                self.getToken()
        return nsId["id"]

    def getNsr(self, nsId):
        """
        Returns the NSR for a given NS ID
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/ns_instances/{nsId}"
        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(osm_url, headers=headers, verify=False)
            try:
                response_data = response.json()
                logger.debug("Received NSR response: %s", json.dumps(response_data, indent=2))
            except ValueError:
                logger.error("Failed to decode JSON from NSR response: %s", response.text)
                return {}
            
            if response.status_code == 200:
                nsr = response_data
                break
            elif response.status_code == 401:
                self.getToken()
            else:
                return {}
        return nsr

    def readVnfd(self):
        """
        Reads and logs information from VNFDs
        """
        url = f"https://{self.ip}/osm/vnfpkgm/v1/vnf_packages/"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(url, headers=headers, verify=False)
    
            try:
                response_data = response.json()
                logger.debug("Received VNFD response: %s", json.dumps(response_data, indent=2))
            except ValueError:
                logger.error("Failed to decode JSON from VNFD response: %s", response.text)
                break
    
            if response.status_code != 401:
                osm_vnfd_list = response_data
                for osm_vnfd in osm_vnfd_list:
                    new_vnfd = {}
                    if all(key in osm_vnfd for key in ("id", "_id", "mgmt-cp", "vdu")):
                        new_vnfd["vnfd-id"] = osm_vnfd["_id"]
                        new_vnfd["name"] = osm_vnfd["id"]
                        new_vnfd["flavor"] = {"memory-mb": 0, "vcpu-count": 0, "storage-gb": 0}
                        instances = 0
    
                        # Iterate over VDUs and calculate resources
                        for vdu in osm_vnfd["vdu"]:
                            logger.debug("Processing VDU: %s", vdu.get("id"))
    
                            # Extract virtual-compute-desc for CPU and memory
                            virtual_compute_id = vdu.get("virtual-compute-desc")
                            if virtual_compute_id:
                                logger.debug("Virtual compute descriptor ID found: %s", virtual_compute_id)
                                virtual_compute = next(
                                    (compute for compute in osm_vnfd.get("virtual-compute-desc", []) if compute["id"] == virtual_compute_id),
                                    None
                                )
                                if virtual_compute:
                                    # Update CPU and memory
                                    vcpu_count = int(virtual_compute.get("virtual-cpu", {}).get("num-virtual-cpu", 0))
                                    memory_mb = int(virtual_compute.get("virtual-memory", {}).get("size", 0))
                                    new_vnfd["flavor"]["vcpu-count"] += vcpu_count
                                    new_vnfd["flavor"]["memory-mb"] += memory_mb * 1024
                                    logger.debug("Updated VCPU count: %d, Memory MB: %d", new_vnfd["flavor"]["vcpu-count"], new_vnfd["flavor"]["memory-mb"])
                                else:
                                    logger.warning("Virtual compute descriptor ID %s not found in VNFD", virtual_compute_id)
    
                            # Extract virtual-storage-desc for storage requirements
                            virtual_storage_ids = vdu.get("virtual-storage-desc", [])
                            if virtual_storage_ids:
                                logger.debug("Virtual storage descriptor IDs found: %s", virtual_storage_ids)
                            for storage_id in virtual_storage_ids:
                                virtual_storage = next(
                                    (storage for storage in osm_vnfd.get("virtual-storage-desc", []) if storage["id"] == storage_id),
                                    None
                                )
                                if virtual_storage:
                                    storage_gb = int(virtual_storage.get("size-of-storage", 0))
                                    new_vnfd["flavor"]["storage-gb"] += storage_gb
                                    logger.debug("Updated Storage GB: %d", new_vnfd["flavor"]["storage-gb"])
                                else:
                                    logger.warning("Virtual storage descriptor ID %s not found in VNFD", storage_id)
    
                            instances += 1
    
                        new_vnfd["flavor"]["instances"] = instances
                        logger.debug("Total instances: %d", new_vnfd["flavor"]["instances"])
                        new_vnfd["mgmt"] = osm_vnfd.get("mgmt-cp", "")
                        new_vnfd["nfvo_id"] = self.nfvo_id
                        new_vnfd["_id"] = str(uuid.uuid4())
    
                        try:
                            mongoUtils.add("vnfd", new_vnfd)
                            logger.debug("Successfully added VNFD to MongoDB: %s", new_vnfd["name"])
                        except pymongo.errors.DuplicateKeyError:
                            logger.warning("VNFD with ID %s already exists in MongoDB. Skipping...", new_vnfd["vnfd-id"])
                            continue
                break
            else:
                logger.warning("Unauthorized response received. Fetching a new token...")
                self.getToken()

        
    def readNsd(self):
        """
        Reads and logs information from NSDs
        """
        url = f"https://{self.ip}/osm/nsd/v1/ns_descriptors"
        while True:
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            response = requests.get(url, headers=headers, verify=False)
    
            try:
                response_data = response.json()
                logger.debug("Received NSD response: %s", json.dumps(response_data, indent=2))
            except ValueError:
                logger.error("Failed to decode JSON from NSD response: %s", response.text)
                break
    
            if response.status_code != 401:
                osm_nsd_list = response_data
                for osm_nsd in osm_nsd_list:
                    logger.debug("Processing NSD: %s", osm_nsd.get("id"))
    
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
    
                    # Iterate over VNFDs that are part of the NSD
                    for osm_vnfd in osm_nsd.get("vnfd-id", []):
                        vnfd_id = osm_vnfd  # This is the VNFD reference used in the NSD
                        logger.debug("Found VNFD reference in NSD: %s", vnfd_id)
    
                        # Try to look up the VNFD in MongoDB by both name and id
                        reg_vnfd = mongoUtils.find("vnfd", {"id": vnfd_id})
                        if not reg_vnfd:
                            # Retry lookup by using "name"
                            reg_vnfd = mongoUtils.find("vnfd", {"name": vnfd_id})
    
                        if reg_vnfd:
                            logger.debug("VNFD found in database: %s", vnfd_id)
                            new_nsd["vnfd_list"].append(reg_vnfd["name"])
    
                            # Aggregate resources from VNFD to NSD
                            for key in new_nsd["flavor"]:
                                if key in reg_vnfd["flavor"]:
                                    logger.debug("Aggregating %s: current value = %d, VNFD contribution = %d",
                                                 key, new_nsd["flavor"][key], reg_vnfd["flavor"][key])
                                    new_nsd["flavor"][key] += reg_vnfd["flavor"][key]
                        else:
                            logger.warning("VNFD with reference '%s' not found in MongoDB. Skipping...", vnfd_id)
    
                    # Log the final aggregated NSD before adding it to the database
                    logger.debug("Final aggregated NSD: %s", json.dumps(new_nsd, indent=2))
    
                    try:
                        mongoUtils.add("nsd", new_nsd)
                        logger.debug("Successfully added NSD to MongoDB: %s", new_nsd["nsd-name"])
                    except pymongo.errors.DuplicateKeyError:
                        logger.warning("NSD with ID %s already exists in MongoDB. Skipping...", new_nsd["nsd-id"])
    
                break
            else:
                logger.warning("Unauthorized response received. Fetching a new token...")
                self.getToken()
    
        


    def bootstrapNfvo(self):
        """
        Reads info from NSDs/VNFDs in the NFVO and stores them in MongoDB
        """
        self.readVnfd()
        self.readNsd()
