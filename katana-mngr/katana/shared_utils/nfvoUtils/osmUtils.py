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

    def getNsr(self, nsId):
        """
        Returns the NSR for a given NS ID
        """
        osm_url = f"https://{self.ip}/osm/nslcm/v1/ns_instances/{nsId}"
        # Get the NSR from NS ID in json format
        for attempt in range(1, OSM_REQUEST_ATTEMPTS + 1):
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
            try:
                response = requests.get(
                    osm_url, headers=headers, verify=self.verify, timeout=self.timeout
                )
                if response.status_code == 401:
                    self.getToken()
                    continue
                response.raise_for_status()
                return response.json()
            except OsmAuthenticationError:
                raise
            except (requests.RequestException, ValueError) as exc:
                logger.warning(
                    "OSM NS status attempt %s/%s failed (%s)",
                    attempt,
                    OSM_REQUEST_ATTEMPTS,
                    type(exc).__name__,
                )
                if attempt < OSM_REQUEST_ATTEMPTS:
                    time.sleep(attempt)
        raise OsmRequestError(
            f"OSM NS status request failed after {OSM_REQUEST_ATTEMPTS} attempts"
        )

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
            response = requests.get(osm_url, headers=headers, verify=self.verify)
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
            response = requests.delete(osm_url, headers=headers, verify=self.verify)
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
            response = requests.delete(osm_url, headers=headers, verify=self.verify)
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
            response = requests.get(url, headers=headers, verify=self.verify)
            if response.status_code != 401:
                try:
                    response_data = response.json()
                    logger.debug("Received VNFD response: %s", json.dumps(response_data, indent=2))
                    osm_vnfd_list = response_data
                    for osm_vnfd in osm_vnfd_list:
                        runtime = classify_workload_descriptor(osm_vnfd)
                        if all(key in osm_vnfd for key in ("id", "_id")) and runtime != "unknown":
                            new_vnfd = {
                                "vnfd-id": osm_vnfd["_id"],
                                "name": osm_vnfd["id"],
                                "flavor": {"memory-mb": 0, "vcpu-count": 0, "storage-gb": 0},
                                "mgmt": (osm_vnfd.get("mgmt-interface") or {}).get("cp", ""),
                                "deployment_runtime": runtime,
                                "nfvo_id": self.nfvo_id,
                                "_id": str(uuid.uuid4()),
                            }
                            instances = 0
                            for vdu in osm_vnfd.get("vdu", []):
                                if "vm-flavor" in vdu.keys():
                                    for key in new_vnfd["flavor"]:
                                        new_vnfd["flavor"][key] += int(vdu["vm-flavor"][key])
                                    instances += 1
                            new_vnfd["flavor"]["instances"] = instances
                            try:
                                mongoUtils.add("vnfd", new_vnfd)
                            except pymongo.errors.DuplicateKeyError:
                                existing = mongoUtils.find("vnfd", {"vnfd-id": new_vnfd["vnfd-id"]})
                                new_vnfd["_id"] = existing["_id"]
                                mongoUtils.update("vnfd", existing["_id"], new_vnfd)
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
            response = requests.get(url, headers=headers, verify=self.verify)
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
                        runtimes = set()
                        vnfd_refs = [
                            item["vnfd-id-ref"]
                            for item in osm_nsd.get("constituent-vnfd", [])
                            if item.get("vnfd-id-ref")
                        ]
                        vnfd_refs.extend(osm_nsd.get("vnfd-id", []))
                        for vnfd_ref in vnfd_refs:
                            data = {"name": vnfd_ref}
                            reg_vnfd = mongoUtils.find("vnfd", data)
                            if reg_vnfd:
                                new_nsd["vnfd_list"].append(reg_vnfd["name"])
                                runtimes.add(reg_vnfd.get("deployment_runtime", "unknown"))
                                for key in new_nsd["flavor"]:
                                    new_nsd["flavor"][key] += reg_vnfd["flavor"][key]
                        if "mixed" in runtimes or len(runtimes - {"unknown"}) > 1:
                            new_nsd["deployment_runtime"] = "mixed"
                        elif runtimes - {"unknown"}:
                            new_nsd["deployment_runtime"] = next(iter(runtimes - {"unknown"}))
                        else:
                            new_nsd["deployment_runtime"] = "unknown"
                        try:
                            mongoUtils.add("nsd", new_nsd)
                        except pymongo.errors.DuplicateKeyError:
                            existing = mongoUtils.find("nsd", {"nsd-id": new_nsd["nsd-id"]})
                            new_nsd["_id"] = existing["_id"]
                            mongoUtils.update("nsd", existing["_id"], new_nsd)
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
            response = requests.get(osm_url, headers=headers, verify=self.verify)
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
