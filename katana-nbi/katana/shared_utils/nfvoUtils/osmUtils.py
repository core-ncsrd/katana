import logging
import logging.handlers
import uuid
import json
import time
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

OSM_REQUEST_ATTEMPTS = 3
OSM_AUTH_TIMEOUT = 20
OSM_WRITE_TIMEOUT = 30


class OsmAuthenticationError(RuntimeError):
    """Raised when OSM authentication still fails after bounded retries."""


class OsmRequestError(RuntimeError):
    """Raised when an OSM operation still fails after bounded retries."""


def classify_workload_descriptor(descriptor):
    """Classify an OSM VNFD as a VM, Kubernetes, mixed, or unknown workload."""
    has_vdu = bool(descriptor.get("vdu"))
    has_kdu = bool(descriptor.get("kdu"))
    if has_vdu and has_kdu:
        return "mixed"
    if has_kdu:
        return "kubernetes"
    if has_vdu:
        return "openstack"
    return "unknown"


class Osm:
    """
    Class implementing the communication API with OSM
    """

    def __init__(
        self,
        nfvo_id,
        ip,
        username,
        password,
        project_id="admin",
        timeout=5,
        verify=True,
    ):
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
        self.verify = verify

    def __setstate__(self, state):
        self.__dict__.update(state)
        if "verify" not in self.__dict__:
            self.verify = False

    def getToken(self):
        """
        Returns a valid Token for OSM
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "username": self.username,
            "password": self.password,
            "project_id": self.project_id,
        }
        url = f"https://{self.ip}/osm/admin/v1/tokens"
        auth_timeout = max(self.timeout, OSM_AUTH_TIMEOUT)
        for attempt in range(1, OSM_REQUEST_ATTEMPTS + 1):
            try:
                response = requests.post(
                    url, headers=headers, json=payload, verify=self.verify, timeout=auth_timeout
                )
                response.raise_for_status()
                response_data = response.json()
                self.token = response_data.get("id") or response_data.get("_id")
                if not self.token:
                    raise ValueError("token id is missing")
                return self.token
            except (requests.RequestException, ValueError, AttributeError) as exc:
                self.token = ""
                logger.warning(
                    "OSM authentication attempt %s/%s failed (%s)",
                    attempt,
                    OSM_REQUEST_ATTEMPTS,
                    type(exc).__name__,
                )
                if attempt < OSM_REQUEST_ATTEMPTS:
                    time.sleep(attempt)
        raise OsmAuthenticationError(
            f"OSM authentication failed after {OSM_REQUEST_ATTEMPTS} attempts"
        )

    def _admin_headers(self):
        if not self.token:
            self.getToken()
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def addVim(
        self,
        vimName,
        vimPassword,
        vimType,
        vimUrl,
        vimUser,
        secGroup,
        vimTenantName=None,
    ):
        """
        Registers a VIM to the OSM VIM account list
        Returns VIM id
        """
        osm_url = f"https://{self.ip}/osm/admin/v1/vim_accounts"
        payload = {
            "name": vimName,
            "vim_password": vimPassword,
            "vim_tenant_name": vimTenantName or vimName,
            "vim_type": vimType,
            "vim_url": vimUrl,
            "vim_user": vimUser,
            "config": secGroup or {},
        }
        write_timeout = max(self.timeout, OSM_WRITE_TIMEOUT)
        for attempt in range(1, OSM_REQUEST_ATTEMPTS + 1):
            if not self.token:
                self.getToken()
            headers = self._admin_headers()
            try:
                response = requests.post(
                    osm_url,
                    headers=headers,
                    json=payload,
                    verify=self.verify,
                    timeout=write_timeout,
                )
                if response.status_code == 401:
                    self.token = ""
                    continue
                response.raise_for_status()
                response_data = response.json()
                vim_id = response_data.get("id") or response_data.get("_id")
                if not vim_id:
                    raise ValueError("VIM account id is missing")
                return vim_id
            except requests.Timeout as exc:
                raise OsmRequestError(
                    f"OSM VIM registration timed out after {write_timeout} seconds"
                ) from exc
            except (requests.RequestException, ValueError, AttributeError) as exc:
                raise OsmRequestError("OSM VIM registration failed") from exc
        raise OsmAuthenticationError(
            f"OSM authentication failed after {OSM_REQUEST_ATTEMPTS} attempts"
        )

    def listVims(self):
        """Return the VIM accounts visible in the configured OSM project."""
        url = f"https://{self.ip}/osm/admin/v1/vim_accounts"
        for _ in range(OSM_REQUEST_ATTEMPTS):
            response = requests.get(
                url,
                headers=self._admin_headers(),
                verify=self.verify,
                timeout=max(self.timeout, OSM_AUTH_TIMEOUT),
            )
            if response.status_code == 401:
                self.token = ""
                continue
            response.raise_for_status()
            return response.json() or []
        raise OsmAuthenticationError(
            f"OSM authentication failed after {OSM_REQUEST_ATTEMPTS} attempts"
        )

    def getVim(self, vim_id):
        """Return one OSM VIM account, or None when it no longer exists."""
        url = f"https://{self.ip}/osm/admin/v1/vim_accounts/{vim_id}"
        for _ in range(OSM_REQUEST_ATTEMPTS):
            response = requests.get(
                url,
                headers=self._admin_headers(),
                verify=self.verify,
                timeout=max(self.timeout, OSM_AUTH_TIMEOUT),
            )
            if response.status_code == 401:
                self.token = ""
                continue
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        raise OsmAuthenticationError(
            f"OSM authentication failed after {OSM_REQUEST_ATTEMPTS} attempts"
        )

    def updateVim(self, vim_id, vim_user, vim_password, config=None):
        """Update mutable credentials/configuration without replacing account identity."""
        url = f"https://{self.ip}/osm/admin/v1/vim_accounts/{vim_id}"
        payload = {
            "vim_user": vim_user,
            "vim_password": vim_password,
            "config": config or {},
        }
        for _ in range(OSM_REQUEST_ATTEMPTS):
            response = requests.patch(
                url,
                headers=self._admin_headers(),
                json=payload,
                verify=self.verify,
                timeout=max(self.timeout, OSM_WRITE_TIMEOUT),
            )
            if response.status_code == 401:
                self.token = ""
                continue
            response.raise_for_status()
            return response.json() if response.content else {}
        raise OsmAuthenticationError(
            f"OSM authentication failed after {OSM_REQUEST_ATTEMPTS} attempts"
        )

    def waitForVim(self, vim_id, attempts=12, interval=5):
        """Wait for OSM validation when the server exposes an operational state."""
        for attempt in range(attempts):
            account = self.getVim(vim_id)
            if not account:
                raise OsmRequestError(f"OSM VIM account {vim_id} disappeared")
            state = (account.get("_admin") or {}).get("operationalState")
            state = str(state or account.get("operationalState") or "").upper()
            if state in {"ENABLED", "RUNNING", "READY"}:
                return account
            if state in {"ERROR", "FAILED", "DISABLED"}:
                detail = (account.get("_admin") or {}).get("detailed-status")
                raise OsmRequestError(
                    f"OSM VIM account {vim_id} failed validation"
                    + (f": {detail}" if detail else "")
                )
            if attempt + 1 < attempts:
                time.sleep(interval)
        raise OsmRequestError(f"OSM VIM account {vim_id} did not become ready")

    def instantiateNs(self, nsName, nsdId, vimAccountId):
        """
        Instantiates a NS on the OSM
        Returns the NS ID
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/ns_instances_content"

        data = "{{ nsName: {0}, nsdId: {1}, vimAccountId: {2} }}".format(
            nsName, nsdId, vimAccountId
        )
        write_timeout = max(self.timeout, OSM_WRITE_TIMEOUT)
        for attempt in range(1, OSM_REQUEST_ATTEMPTS + 1):
            if not self.token:
                self.getToken()
            headers = {
                "Content-Type": "application/yaml",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            try:
                response = requests.post(
                    osm_url,
                    headers=headers,
                    data=data,
                    verify=self.verify,
                    timeout=write_timeout,
                )
                if response.status_code == 401:
                    self.token = ""
                    continue
                response.raise_for_status()
                response_data = response.json()
                ns_id = response_data.get("id") or response_data.get("_id")
                if not ns_id:
                    raise ValueError("NS instance id is missing")
                return ns_id
            except requests.Timeout as exc:
                raise OsmRequestError(
                    f"OSM NS instantiation timed out after {write_timeout} seconds"
                ) from exc
            except (requests.RequestException, ValueError, AttributeError) as exc:
                raise OsmRequestError("OSM NS instantiation failed") from exc
        raise OsmAuthenticationError(
            f"OSM authentication failed after {OSM_REQUEST_ATTEMPTS} attempts"
        )

    def addK8sCluster(self, payload):
        """Register a Kubernetes cluster with OSM and return its response."""
        url = f"https://{self.ip}/osm/admin/v1/k8sclusters"
        while True:
            response = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
                json=payload,
                verify=self.verify,
                timeout=self.timeout,
            )
            if response.status_code == 401:
                self.getToken()
                continue
            response.raise_for_status()
            return response.json()

    def deleteK8sCluster(self, cluster_id):
        """Remove a Kubernetes cluster registration from OSM."""
        url = f"https://{self.ip}/osm/admin/v1/k8sclusters/{cluster_id}"
        while True:
            response = requests.delete(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                verify=self.verify,
                timeout=self.timeout,
            )
            if response.status_code == 401:
                self.getToken()
                continue
            response.raise_for_status()
            return

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
            response = requests.get(osm_url, headers=headers, verify=self.verify)
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
            response = requests.get(url, headers=headers, verify=self.verify)
    
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
                    runtime = classify_workload_descriptor(osm_vnfd)
                    if all(key in osm_vnfd for key in ("id", "_id")) and runtime != "unknown":
                        new_vnfd["vnfd-id"] = osm_vnfd["_id"]
                        new_vnfd["name"] = osm_vnfd["id"]
                        new_vnfd["flavor"] = {"memory-mb": 0, "vcpu-count": 0, "storage-gb": 0}
                        instances = 0
    
                        # Iterate over VDUs and calculate resources
                        for vdu in osm_vnfd.get("vdu", []):
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
                        new_vnfd["deployment_runtime"] = runtime
                        new_vnfd["nfvo_id"] = self.nfvo_id
                        new_vnfd["_id"] = str(uuid.uuid4())
    
                        try:
                            mongoUtils.add("vnfd", new_vnfd)
                            logger.debug("Successfully added VNFD to MongoDB: %s", new_vnfd["name"])
                        except pymongo.errors.DuplicateKeyError:
                            existing = mongoUtils.find("vnfd", {"vnfd-id": new_vnfd["vnfd-id"]})
                            new_vnfd["_id"] = existing["_id"]
                            mongoUtils.update("vnfd", existing["_id"], new_vnfd)
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
            response = requests.get(url, headers=headers, verify=self.verify)
    
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
                    runtimes = set()
    
                    # Iterate over VNFDs that are part of the NSD
                    vnfd_refs = list(osm_nsd.get("vnfd-id", []))
                    vnfd_refs.extend(
                        item.get("vnfd-id-ref")
                        for item in osm_nsd.get("constituent-vnfd", [])
                        if item.get("vnfd-id-ref")
                    )
                    for vnfd_id in vnfd_refs:
                        logger.debug("Found VNFD reference in NSD: %s", vnfd_id)
    
                        # Try to look up the VNFD in MongoDB by both name and id
                        reg_vnfd = mongoUtils.find("vnfd", {"id": vnfd_id})
                        if not reg_vnfd:
                            # Retry lookup by using "name"
                            reg_vnfd = mongoUtils.find("vnfd", {"name": vnfd_id})
    
                        if reg_vnfd:
                            logger.debug("VNFD found in database: %s", vnfd_id)
                            new_nsd["vnfd_list"].append(reg_vnfd["name"])
                            runtimes.add(reg_vnfd.get("deployment_runtime", "unknown"))
    
                            # Aggregate resources from VNFD to NSD
                            for key in new_nsd["flavor"]:
                                if key in reg_vnfd["flavor"]:
                                    logger.debug("Aggregating %s: current value = %d, VNFD contribution = %d",
                                                 key, new_nsd["flavor"][key], reg_vnfd["flavor"][key])
                                    new_nsd["flavor"][key] += reg_vnfd["flavor"][key]
                        else:
                            logger.warning("VNFD with reference '%s' not found in MongoDB. Skipping...", vnfd_id)

                    if "mixed" in runtimes or len(runtimes - {"unknown"}) > 1:
                        new_nsd["deployment_runtime"] = "mixed"
                    elif runtimes - {"unknown"}:
                        new_nsd["deployment_runtime"] = next(iter(runtimes - {"unknown"}))
                    else:
                        new_nsd["deployment_runtime"] = "unknown"
    
                    # Log the final aggregated NSD before adding it to the database
                    logger.debug("Final aggregated NSD: %s", json.dumps(new_nsd, indent=2))
    
                    try:
                        mongoUtils.add("nsd", new_nsd)
                        logger.debug("Successfully added NSD to MongoDB: %s", new_nsd["nsd-name"])
                    except pymongo.errors.DuplicateKeyError:
                        existing = mongoUtils.find("nsd", {"nsd-id": new_nsd["nsd-id"]})
                        new_nsd["_id"] = existing["_id"]
                        mongoUtils.update("nsd", existing["_id"], new_nsd)
    
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
