import copy
import pickle
from pathlib import Path
import time
import uuid

from bson.binary import Binary
import pymongo
import yaml

from katana.shared_utils.infrastructureUtils import (
    InfrastructureError,
    _ensure_location,
    _openstack_auth,
)
from katana.shared_utils.mongoUtils import mongoUtils
from katana.shared_utils.nfvoUtils import osmUtils
from katana.shared_utils.vimUtils import openstackUtils


LOCK_ID = "infrastructure-bootstrap"
LOCK_SECONDS = 900
REDACTED_FIELDS = {"password", "nfvopassword", "credentials", "obj"}


class BootstrapError(Exception):
    def __init__(self, message, status_code=400, results=None):
        super().__init__(message)
        self.status_code = status_code
        self.results = results or []


def load_manifest_file(filename):
    """Load a versioned manifest and resolve credential files beside it."""
    path = Path(filename).resolve()
    try:
        with path.open() as stream:
            manifest = yaml.safe_load(stream)
    except FileNotFoundError as exc:
        raise BootstrapError(f"Bootstrap manifest {filename} was not found") from exc
    except yaml.YAMLError as exc:
        raise BootstrapError(f"Unable to parse bootstrap manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BootstrapError("Bootstrap manifest must be an object")

    root = path.parent
    resolved = copy.deepcopy(manifest)
    for kind in ("nfvos", "vims"):
        entries = resolved.get(kind, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            reference = entry.pop("credentials_file", None)
            if not reference:
                raise BootstrapError(
                    f"{kind[:-1].upper()} {entry.get('id', '<unknown>')} requires credentials_file"
                )
            credential_path = (root / reference).resolve()
            try:
                credential_path.relative_to(root)
            except ValueError as exc:
                raise BootstrapError(
                    f"Credential path for {entry.get('id', '<unknown>')} leaves the manifest directory"
                ) from exc
            try:
                with credential_path.open() as stream:
                    credentials = yaml.safe_load(stream)
            except FileNotFoundError as exc:
                raise BootstrapError(f"Credential file {reference} was not found") from exc
            except yaml.YAMLError as exc:
                raise BootstrapError(
                    f"Unable to parse credential file {reference}: {exc}"
                ) from exc
            if not isinstance(credentials, dict):
                raise BootstrapError(f"Credential file {reference} must contain an object")
            entry["credentials"] = credentials
            if kind == "vims" and credentials.get("clouds"):
                cloud_name = entry.get("cloud") or next(iter(credentials["clouds"]))
                cloud = credentials["clouds"].get(cloud_name, {})
                if cloud.get("cacert") and not Path(cloud["cacert"]).is_absolute():
                    ca_path = (credential_path.parent / cloud["cacert"]).resolve()
                    try:
                        ca_path.relative_to(root)
                    except ValueError as exc:
                        raise BootstrapError(
                            f"OpenStack CA path for {entry.get('id')} leaves the manifest directory"
                        ) from exc
                    if not ca_path.is_file():
                        raise BootstrapError(f"CA file {cloud['cacert']} was not found")
                    cloud["cacert"] = str(ca_path)
            if entry.get("ca_file"):
                ca_path = (root / entry["ca_file"]).resolve()
                try:
                    ca_path.relative_to(root)
                except ValueError as exc:
                    raise BootstrapError(
                        f"CA path for {entry.get('id', '<unknown>')} leaves the manifest directory"
                    ) from exc
                if not ca_path.is_file():
                    raise BootstrapError(f"CA file {entry['ca_file']} was not found")
                entry["ca_file"] = str(ca_path)
    return validate_manifest(resolved)


def public_record(record):
    """Return configuration data without credential material or pickled objects."""
    if isinstance(record, dict):
        return {
            key: public_record(value)
            for key, value in record.items()
            if str(key).lower() not in REDACTED_FIELDS
        }
    if isinstance(record, list):
        return [public_record(value) for value in record]
    return record


def _required(data, fields, label):
    missing = [field for field in fields if not data.get(field)]
    if missing:
        raise BootstrapError(f"{label} is missing: {', '.join(missing)}")


def _string_fields(data, fields, label):
    invalid = [field for field in fields if not isinstance(data.get(field), str)]
    if invalid:
        raise BootstrapError(f"{label} fields must be strings: {', '.join(invalid)}")


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise BootstrapError("Bootstrap manifest must be an object")
    if manifest.get("api_version") != "katana/v1":
        raise BootstrapError("Unsupported bootstrap api_version; expected katana/v1")

    nfvos = manifest.get("nfvos", [])
    vims = manifest.get("vims", [])
    if not isinstance(nfvos, list) or not isinstance(vims, list):
        raise BootstrapError("Bootstrap fields nfvos and vims must be arrays")
    if not nfvos:
        raise BootstrapError("Bootstrap manifest must configure at least one NFVO")
    if not vims:
        raise BootstrapError("Bootstrap manifest must configure at least one VIM")

    nfvo_ids = set()
    for nfvo in nfvos:
        if not isinstance(nfvo, dict):
            raise BootstrapError("Every NFVO entry must be an object")
        _required(nfvo, ("id", "type", "endpoint", "project", "credentials"), "NFVO")
        _string_fields(nfvo, ("id", "type", "endpoint", "project"), "NFVO")
        if str(nfvo["type"]).lower() != "osm":
            raise BootstrapError(f"NFVO {nfvo['id']} has unsupported type {nfvo['type']}")
        credentials = nfvo["credentials"]
        if not isinstance(credentials, dict):
            raise BootstrapError(f"NFVO {nfvo['id']} credentials must be an object")
        _required(credentials, ("username", "password"), f"NFVO {nfvo['id']} credentials")
        _string_fields(
            credentials,
            ("username", "password"),
            f"NFVO {nfvo['id']} credentials",
        )
        if not isinstance(nfvo.get("tls_verify", True), bool):
            raise BootstrapError(f"NFVO {nfvo['id']} tls_verify must be true or false")
        if nfvo.get("ca_file") is not None and not isinstance(nfvo["ca_file"], str):
            raise BootstrapError(f"NFVO {nfvo['id']} ca_file must be a path")
        if nfvo.get("ca_file") and nfvo.get("tls_verify") is False:
            raise BootstrapError(
                f"NFVO {nfvo['id']} cannot set both ca_file and tls_verify false"
            )
        if nfvo["id"] in nfvo_ids:
            raise BootstrapError(f"Duplicate NFVO id {nfvo['id']}")
        nfvo_ids.add(nfvo["id"])

    vim_ids = set()
    account_names = set()
    for vim in vims:
        if not isinstance(vim, dict):
            raise BootstrapError("Every VIM entry must be an object")
        _required(vim, ("id", "type", "location", "credentials"), "VIM")
        _string_fields(vim, ("id", "type", "location"), "VIM")
        if vim.get("cloud") is not None and not isinstance(vim["cloud"], str):
            raise BootstrapError(f"VIM {vim['id']} cloud must be a string")
        if str(vim["type"]).lower() != "openstack":
            raise BootstrapError(f"VIM {vim['id']} has unsupported type {vim['type']}")
        if vim["id"] in vim_ids:
            raise BootstrapError(f"Duplicate VIM id {vim['id']}")
        vim_ids.add(vim["id"])
        try:
            auth = _openstack_auth(vim)
        except InfrastructureError as exc:
            raise BootstrapError(str(exc), exc.status_code) from exc
        _string_fields(
            auth,
            ("auth_url", "username", "password", "admin_project_name"),
            f"VIM {vim['id']} credentials",
        )
        cloud = _selected_cloud(vim)
        if not isinstance(cloud.get("verify", True), bool):
            raise BootstrapError(f"VIM {vim['id']} verify must be true or false")
        if cloud.get("cacert") is not None and not isinstance(cloud["cacert"], str):
            raise BootstrapError(f"VIM {vim['id']} cacert must be a path")
        if cloud.get("cacert") and cloud.get("verify") is False:
            raise BootstrapError(
                f"VIM {vim['id']} cannot set both cacert and verify false"
            )
        links = vim.get("nfvos", [])
        if not isinstance(links, list) or not links:
            raise BootstrapError(f"VIM {vim['id']} must link at least one NFVO")
        linked_nfvos = set()
        for link in links:
            if not isinstance(link, dict):
                raise BootstrapError(f"VIM {vim['id']} NFVO links must be objects")
            _required(link, ("id",), f"VIM {vim['id']} NFVO link")
            _string_fields(link, ("id",), f"VIM {vim['id']} NFVO link")
            if link.get("account_name") is not None and not isinstance(
                link["account_name"], str
            ):
                raise BootstrapError(
                    f"VIM {vim['id']} NFVO account_name must be a string"
                )
            if not isinstance(link.get("config", {}), dict):
                raise BootstrapError(f"VIM {vim['id']} NFVO config must be an object")
            if link["id"] not in nfvo_ids:
                raise BootstrapError(
                    f"VIM {vim['id']} references unknown NFVO {link['id']}"
                )
            if link["id"] in linked_nfvos:
                raise BootstrapError(
                    f"VIM {vim['id']} links NFVO {link['id']} more than once"
                )
            linked_nfvos.add(link["id"])
            account_name = link.get("account_name") or f"katana-{link['id']}-{vim['id']}"
            account_key = (link["id"], account_name)
            if account_key in account_names:
                raise BootstrapError(
                    f"OSM account name {account_name} is duplicated for NFVO {link['id']}"
                )
            account_names.add(account_key)
    return copy.deepcopy(manifest)


def _acquire_lock(owner):
    now = time.time()
    existing = mongoUtils.get("bootstrap_locks", LOCK_ID)
    if existing and existing.get("expires_at", 0) > now:
        raise BootstrapError("Another infrastructure bootstrap is running", 409)
    if existing:
        mongoUtils.delete("bootstrap_locks", LOCK_ID)
    try:
        mongoUtils.add(
            "bootstrap_locks",
            {"_id": LOCK_ID, "owner": owner, "expires_at": now + LOCK_SECONDS},
        )
    except pymongo.errors.DuplicateKeyError as exc:
        raise BootstrapError("Another infrastructure bootstrap is running", 409) from exc


def _store_status(status):
    status = dict(status, _id="latest")
    if mongoUtils.get("bootstrap_status", "latest"):
        mongoUtils.update("bootstrap_status", "latest", status)
    else:
        mongoUtils.add("bootstrap_status", status)


def _nfvo_client(data):
    credentials = data["credentials"]
    return osmUtils.Osm(
        data["id"],
        data["endpoint"],
        credentials["username"],
        credentials["password"],
        data["project"],
        verify=data.get("ca_file") or data.get("tls_verify", True),
    )


def _ensure_nfvo(data):
    if str(data.get("type", "")).lower() != "osm":
        raise BootstrapError(f"NFVO {data.get('id')} has unsupported type {data.get('type')}")
    client = _nfvo_client(data)
    try:
        client.getToken()
    except Exception as exc:
        raise BootstrapError(
            f"Unable to authenticate with NFVO {data['id']}: {exc}", 502
        ) from exc
    existing = mongoUtils.find("nfvo", {"id": data["id"]})
    identity = {
        "type": "OSM",
        "nfvoip": data["endpoint"],
        "tenantname": data["project"],
    }
    if existing:
        actual = {key: existing.get(key) for key in identity}
        actual["type"] = str(actual["type"] or "").upper()
        if actual != identity:
            raise BootstrapError(
                f"NFVO {data['id']} is registered with different identity settings", 409
            )
        changed = any(
            (
                existing.get("name") != data.get("name", existing.get("name", data["id"])),
                existing.get("description", "") != data.get("description", ""),
                existing.get("nfvousername") != data["credentials"]["username"],
                existing.get("nfvopassword") != data["credentials"]["password"],
                existing.get("tls_verify", True) != data.get("tls_verify", True),
                existing.get("ca_file") != data.get("ca_file"),
            )
        )
        record = dict(existing)
        record.update(
            {
                "name": data.get("name", existing.get("name", data["id"])),
                "nfvousername": data["credentials"]["username"],
                "nfvopassword": data["credentials"]["password"],
                "tls_verify": data.get("tls_verify", True),
                "ca_file": data.get("ca_file"),
            }
        )
        mongoUtils.update("nfvo", existing["_id"], record)
        obj = mongoUtils.find("nfvo_obj", {"id": data["id"]})
        obj_record = {
            "_id": obj["_id"] if obj else existing["_id"],
            "id": data["id"],
            "obj": Binary(pickle.dumps(client)),
        }
        if obj:
            mongoUtils.update("nfvo_obj", obj["_id"], obj_record)
        else:
            mongoUtils.add("nfvo_obj", obj_record)
        return record, client, "updated" if changed else "unchanged"

    db_id = str(uuid.uuid4())
    record = {
        "_id": db_id,
        "id": data["id"],
        "name": data.get("name", data["id"]),
        "type": "OSM",
        "nfvoip": data["endpoint"],
        "nfvousername": data["credentials"]["username"],
        "nfvopassword": data["credentials"]["password"],
        "tenantname": data["project"],
        "tls_verify": data.get("tls_verify", True),
        "ca_file": data.get("ca_file"),
        "description": data.get("description", ""),
        "created_at": time.time(),
        "tenants": {},
    }
    mongoUtils.add("nfvo", record)
    try:
        mongoUtils.add(
            "nfvo_obj",
            {"_id": db_id, "id": data["id"], "obj": Binary(pickle.dumps(client))},
        )
    except Exception:
        mongoUtils.delete("nfvo", db_id)
        raise
    return record, client, "created"


def _selected_cloud(data):
    clouds = data["credentials"].get("clouds", {})
    if not clouds:
        return {"verify": data.get("verify", True)}
    cloud_name = data.get("cloud") or next(iter(clouds))
    return clouds[cloud_name]


def _ensure_vim(data):
    if str(data.get("type", "")).lower() != "openstack":
        raise BootstrapError(f"VIM {data.get('id')} has unsupported type {data.get('type')}")
    auth = _openstack_auth(data)
    cloud = _selected_cloud(data)
    verify = cloud.get("cacert") or cloud.get("verify", True)
    try:
        client = openstackUtils.Openstack(
            uuid=str(uuid.uuid4()),
            auth_url=auth["auth_url"],
            project_name=auth["admin_project_name"],
            username=auth["username"],
            password=auth["password"],
            verify=verify,
        )
        if client.auth_error:
            raise BootstrapError(
                f"Unable to authenticate with OpenStack VIM {data['id']}", 502
            )
        resources = client.get_resources()
    except BootstrapError:
        raise
    except Exception as exc:
        raise BootstrapError(
            f"Unable to validate OpenStack VIM {data['id']}: {exc}", 502
        ) from exc
    location = _ensure_location(data["location"])
    existing = mongoUtils.find("vim", {"id": data["id"]})
    identity = {
        "type": "openstack",
        "location": data["location"].lower(),
        "auth_url": auth["auth_url"].rstrip("/"),
        "admin_project_name": auth["admin_project_name"],
    }
    if existing:
        actual = {
            key: str(existing.get(key, "")).lower()
            if key == "type"
            else str(existing.get(key, "")).rstrip("/")
            if key == "auth_url"
            else existing.get(key)
            for key in identity
        }
        if actual != identity:
            raise BootstrapError(
                f"VIM {data['id']} is registered with different identity settings", 409
            )
        credentials_changed = (
            existing.get("username") != auth["username"]
            or existing.get("password") != auth["password"]
        )
        record_changed = any(
            (
                credentials_changed,
                existing.get("name") != data.get("name", existing.get("name", data["id"])),
                existing.get("description", "") != data.get("description", ""),
                existing.get("verify", True) != verify,
            )
        )
        record = dict(existing)
        record.update(
            {
                "name": data.get("name", existing.get("name", data["id"])),
                "username": auth["username"],
                "password": auth["password"],
                "resources": resources,
                "verify": verify,
                "description": data.get("description", ""),
            }
        )
        mongoUtils.update("vim", existing["_id"], record)
        obj = mongoUtils.find("vim_obj", {"id": data["id"]})
        obj_record = {
            "_id": obj["_id"] if obj else existing["_id"],
            "id": data["id"],
            "obj": Binary(pickle.dumps(client)),
        }
        if obj:
            mongoUtils.update("vim_obj", obj["_id"], obj_record)
        else:
            mongoUtils.add("vim_obj", obj_record)
        if data["id"] not in location["vims"]:
            location["vims"].append(data["id"])
            mongoUtils.update("location", location["_id"], location)
        return record, "updated" if record_changed else "unchanged", credentials_changed

    db_id = str(uuid.uuid4())
    client.uuid = db_id
    record = {
        "_id": db_id,
        "id": data["id"],
        "name": data.get("name", data["id"]),
        "type": "openstack",
        "location": data["location"].lower(),
        "auth_url": auth["auth_url"],
        "admin_project_name": auth["admin_project_name"],
        "username": auth["username"],
        "password": auth["password"],
        "verify": verify,
        "description": data.get("description", ""),
        "resources": resources,
        "created_at": time.time(),
        "tenants": {},
    }
    mongoUtils.add("vim", record)
    try:
        mongoUtils.add(
            "vim_obj",
            {"_id": db_id, "id": data["id"], "obj": Binary(pickle.dumps(client))},
        )
    except Exception:
        mongoUtils.delete("vim", db_id)
        raise
    if data["id"] not in location["vims"]:
        location["vims"].append(data["id"])
        mongoUtils.update("location", location["_id"], location)
    return record, "created", True


def _account_identity(account):
    return {
        "name": account.get("name"),
        "vim_type": str(account.get("vim_type", "")).lower(),
        "vim_url": str(account.get("vim_url", "")).rstrip("/"),
        "vim_tenant_name": account.get("vim_tenant_name"),
    }


def _ensure_link(nfvo, vim, link, client, credentials_changed=False):
    account_name = link.get("account_name") or f"katana-{nfvo['id']}-{vim['id']}"
    desired = {
        "name": account_name,
        "vim_type": "openstack",
        "vim_url": vim["auth_url"].rstrip("/"),
        "vim_tenant_name": vim["admin_project_name"],
    }
    stored = mongoUtils.find(
        "nfvo_vim_links", {"nfvo_id": nfvo["id"], "vim_id": vim["id"]}
    )
    remote = None
    if stored:
        remote = client.getVim(stored["osm_vim_account_id"])
    if not remote:
        matches = [
            account for account in client.listVims() if account.get("name") == account_name
        ]
        if len(matches) > 1:
            raise BootstrapError(
                f"OSM has multiple VIM accounts named {account_name}", 409
            )
        remote = matches[0] if matches else None

    config = link.get("config", {})
    action = "unchanged"
    if remote:
        if _account_identity(remote) != desired:
            raise BootstrapError(
                f"OSM VIM account {account_name} has conflicting identity settings", 409
            )
        remote_id = remote.get("_id") or remote.get("id")
        recovered = bool(stored and stored.get("osm_vim_account_id") != remote_id)
        if credentials_changed or (stored and stored.get("config", {}) != config):
            client.updateVim(
                remote_id,
                vim_user=vim["username"],
                vim_password=vim["password"],
                config=config,
            )
            action = "updated"
        elif not stored or recovered:
            action = "adopted"
    else:
        remote_id = client.addVim(
            account_name,
            vim["password"],
            "openstack",
            vim["auth_url"],
            vim["username"],
            config,
            vimTenantName=vim["admin_project_name"],
        )
        action = "created"
    client.waitForVim(remote_id)

    now = time.time()
    record = {
        "_id": stored["_id"] if stored else str(uuid.uuid4()),
        "nfvo_id": nfvo["id"],
        "vim_id": vim["id"],
        "osm_vim_account_id": remote_id,
        "osm_vim_account_name": account_name,
        "config": config,
        "managed_by": "bootstrap",
        "management_status": "ready",
        "created_at": stored.get("created_at", now) if stored else now,
        "updated_at": now,
    }
    if stored:
        mongoUtils.update("nfvo_vim_links", stored["_id"], record)
    else:
        mongoUtils.add("nfvo_vim_links", record)
    return record, action


def reconcile_manifest(manifest):
    manifest = validate_manifest(manifest)
    owner = str(uuid.uuid4())
    results = []
    started_at = time.time()
    _acquire_lock(owner)
    try:
        nfvos = {}
        clients = {}
        for data in manifest["nfvos"]:
            record, client, action = _ensure_nfvo(data)
            nfvos[data["id"]] = record
            clients[data["id"]] = client
            results.append({"kind": "nfvo", "id": data["id"], "action": action})

        vims = {}
        credential_changes = {}
        for data in manifest["vims"]:
            record, action, changed = _ensure_vim(data)
            vims[data["id"]] = record
            credential_changes[data["id"]] = changed
            results.append({"kind": "vim", "id": data["id"], "action": action})

        for data in manifest["vims"]:
            for link in data["nfvos"]:
                record, action = _ensure_link(
                    nfvos[link["id"]],
                    vims[data["id"]],
                    link,
                    clients[link["id"]],
                    credential_changes[data["id"]],
                )
                results.append(
                    {
                        "kind": "nfvo_vim_link",
                        "id": f"{record['nfvo_id']}:{record['vim_id']}",
                        "action": action,
                    }
                )

        for nfvo_id, client in clients.items():
            client.bootstrapNfvo()
            results.append({"kind": "descriptors", "id": nfvo_id, "action": "updated"})

        status = {
            "status": "succeeded",
            "started_at": started_at,
            "finished_at": time.time(),
            "results": results,
        }
        _store_status(status)
        return status
    except BootstrapError as exc:
        exc.results = results
        _store_status(
            {
                "status": "failed",
                "started_at": started_at,
                "finished_at": time.time(),
                "results": results,
                "error": str(exc),
            }
        )
        raise
    except Exception as exc:
        error = BootstrapError(str(exc), 502, results)
        _store_status(
            {
                "status": "failed",
                "started_at": started_at,
                "finished_at": time.time(),
                "results": results,
                "error": str(error),
            }
        )
        raise error from exc
    finally:
        lock = mongoUtils.get("bootstrap_locks", LOCK_ID)
        if lock and lock.get("owner") == owner:
            mongoUtils.delete("bootstrap_locks", LOCK_ID)
