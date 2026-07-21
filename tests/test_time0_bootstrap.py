import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import uuid

from tests.test_unified_infrastructure import (
    ClickStub,
    MongoStub,
    PymongoStub,
    load_definitions,
)


class YamlStub:
    class YAMLError(Exception):
        pass

    @staticmethod
    def safe_load(stream):
        return json.load(stream)

    @staticmethod
    def safe_dump(data):
        return json.dumps(data)


def openstack_auth(data):
    clouds = data["credentials"]["clouds"]
    cloud = clouds[data.get("cloud") or next(iter(clouds))]
    auth = cloud["auth"]
    return {
        "auth_url": auth["auth_url"],
        "username": auth["username"],
        "password": auth["password"],
        "admin_project_name": auth["project_name"],
    }


def manifest():
    return {
        "api_version": "katana/v1",
        "nfvos": [
            {
                "id": "osm-main",
                "type": "osm",
                "endpoint": "osm.example",
                "project": "admin",
                "credentials": {"username": "admin", "password": "secret"},
            }
        ],
        "vims": [
            {
                "id": "core-openstack",
                "type": "openstack",
                "location": "core",
                "cloud": "katana",
                "credentials": {
                    "clouds": {
                        "katana": {
                            "auth": {
                                "auth_url": "https://openstack/v3",
                                "username": "katana",
                                "password": "secret",
                                "project_name": "katana-project",
                            }
                        }
                    }
                },
                "nfvos": [{"id": "osm-main", "account_name": "katana-link"}],
            }
        ],
    }


class ManifestValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = load_definitions(
            "katana-nbi/katana/shared_utils/bootstrapUtils.py",
            {
                "BootstrapError",
                "_required",
                "_string_fields",
                "_selected_cloud",
                "validate_manifest",
                "load_manifest_file",
            },
            {
                "copy": copy,
                "Path": Path,
                "yaml": YamlStub,
                "_openstack_auth": openstack_auth,
                "InfrastructureError": RuntimeError,
            },
        )

    def test_versioned_manifest_is_accepted_without_mutation(self):
        source = manifest()
        result = self.namespace["validate_manifest"](source)
        self.assertEqual(result, source)
        self.assertIsNot(result, source)

    def test_duplicate_nfvo_is_rejected_before_reconciliation(self):
        source = manifest()
        source["nfvos"].append(copy.deepcopy(source["nfvos"][0]))
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

    def test_unknown_nfvo_link_is_rejected(self):
        source = manifest()
        source["vims"][0]["nfvos"][0]["id"] = "missing"
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

    def test_invalid_tls_settings_are_rejected(self):
        source = manifest()
        source["nfvos"][0]["tls_verify"] = "false"
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

        source = manifest()
        source["vims"][0]["credentials"]["clouds"]["katana"]["verify"] = "false"
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

    def test_empty_bootstrap_is_rejected(self):
        source = manifest()
        source["nfvos"] = []
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

    def test_malformed_ids_and_link_config_are_rejected_cleanly(self):
        source = manifest()
        source["nfvos"][0]["id"] = ["not", "an", "id"]
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

        source = manifest()
        source["vims"][0]["nfvos"][0]["config"] = ["not", "an", "object"]
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

        source = manifest()
        source["vims"] = []
        with self.assertRaises(self.namespace["BootstrapError"]):
            self.namespace["validate_manifest"](source)

    def test_many_to_many_links_are_accepted(self):
        source = manifest()
        second_nfvo = copy.deepcopy(source["nfvos"][0])
        second_nfvo["id"] = "osm-backup"
        source["nfvos"].append(second_nfvo)
        source["vims"][0]["nfvos"].append(
            {"id": "osm-backup", "account_name": "katana-backup-core"}
        )
        second_vim = copy.deepcopy(source["vims"][0])
        second_vim["id"] = "edge-openstack"
        second_vim["location"] = "edge"
        second_vim["nfvos"] = [
            {"id": "osm-main", "account_name": "katana-main-edge"},
            {"id": "osm-backup", "account_name": "katana-backup-edge"},
        ]
        source["vims"].append(second_vim)

        result = self.namespace["validate_manifest"](source)

        self.assertEqual(len(result["nfvos"]), 2)
        self.assertEqual(sum(len(vim["nfvos"]) for vim in result["vims"]), 4)

    def test_credential_files_are_resolved_relative_to_manifest(self):
        source = manifest()
        source["nfvos"][0].pop("credentials")
        source["nfvos"][0]["credentials_file"] = "secrets/osm.yaml"
        source["vims"][0].pop("credentials")
        source["vims"][0]["credentials_file"] = "secrets/clouds.yaml"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "secrets").mkdir()
            (root / "secrets/osm.yaml").write_text(
                json.dumps({"username": "admin", "password": "secret"})
            )
            (root / "secrets/clouds.yaml").write_text(
                json.dumps(manifest()["vims"][0]["credentials"])
            )
            path = root / "bootstrap.yaml"
            path.write_text(json.dumps(source))
            loaded = self.namespace["load_manifest_file"](path)

        self.assertEqual(loaded["nfvos"][0]["credentials"]["password"], "secret")
        self.assertNotIn("credentials_file", loaded["vims"][0])

    def test_credential_path_cannot_leave_manifest_directory(self):
        source = manifest()
        source["nfvos"][0].pop("credentials")
        source["nfvos"][0]["credentials_file"] = "../osm.yaml"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bootstrap.yaml"
            path.write_text(json.dumps(source))
            with self.assertRaises(self.namespace["BootstrapError"]):
                self.namespace["load_manifest_file"](path)


class CliManifestTests(unittest.TestCase):
    def test_custom_ca_is_mapped_to_the_server_mount(self):
        namespace = load_definitions(
            "katana-cli/cli/commands/cmd_bootstrap.py",
            {"load_bootstrap_data"},
            {"click": ClickStub, "yaml": YamlStub, "os": os},
        )
        source = manifest()
        source["nfvos"][0].pop("credentials")
        source["nfvos"][0]["credentials_file"] = "secrets/osm.yaml"
        source["vims"][0].pop("credentials")
        source["vims"][0]["credentials_file"] = "secrets/clouds.yaml"
        clouds = manifest()["vims"][0]["credentials"]
        clouds["clouds"]["katana"]["cacert"] = "ca.pem"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secrets = root / "secrets"
            secrets.mkdir()
            (secrets / "osm.yaml").write_text(
                json.dumps({"username": "admin", "password": "secret"})
            )
            (secrets / "clouds.yaml").write_text(json.dumps(clouds))
            (secrets / "ca.pem").write_text("test-ca")
            path = root / "bootstrap.yaml"
            path.write_text(json.dumps(source))

            result = namespace["load_bootstrap_data"](str(path))

        self.assertEqual(
            result["vims"][0]["credentials"]["clouds"]["katana"]["cacert"],
            "/bootstrap/secrets/ca.pem",
        )


class OsmStub:
    def __init__(self):
        self.accounts = {}
        self.created_payload = None
        self.updated = False

    def getVim(self, vim_id):
        return self.accounts.get(vim_id)

    def listVims(self):
        return list(self.accounts.values())

    def addVim(self, name, password, vim_type, url, user, config, vimTenantName=None):
        self.created_payload = {
            "name": name,
            "tenant": vimTenantName,
            "config": config,
        }
        account = {
            "_id": "osm-account",
            "name": name,
            "vim_type": vim_type,
            "vim_url": url,
            "vim_tenant_name": vimTenantName,
        }
        self.accounts["osm-account"] = account
        return "osm-account"

    def updateVim(self, *args, **kwargs):
        self.updated = True

    def waitForVim(self, vim_id):
        return self.accounts[vim_id]


class LinkReconciliationTests(unittest.TestCase):
    def _link_namespace(self, mongo):
        return load_definitions(
            "katana-nbi/katana/shared_utils/bootstrapUtils.py",
            {"BootstrapError", "_account_identity", "_ensure_link"},
            {"mongoUtils": mongo, "time": time, "uuid": uuid},
        )

    def _ensure_link(self, mongo):
        return self._link_namespace(mongo)["_ensure_link"]

    def test_link_creation_uses_configured_openstack_project(self):
        mongo = MongoStub()
        osm = OsmStub()
        ensure_link = self._ensure_link(mongo)
        nfvo = {"id": "osm-main"}
        vim = {
            "id": "core-openstack",
            "auth_url": "https://openstack/v3",
            "admin_project_name": "katana-project",
            "username": "katana",
            "password": "secret",
        }

        record, action = ensure_link(
            nfvo,
            vim,
            {"id": "osm-main", "account_name": "katana-link"},
            osm,
        )

        self.assertEqual(action, "created")
        self.assertEqual(osm.created_payload["tenant"], "katana-project")
        self.assertEqual(record["osm_vim_account_id"], "osm-account")
        self.assertEqual(record["management_status"], "ready")

        _, second_action = ensure_link(
            nfvo,
            vim,
            {"id": "osm-main", "account_name": "katana-link"},
            osm,
        )
        self.assertEqual(second_action, "unchanged")
        self.assertEqual(len(mongo.collections["nfvo_vim_links"]), 1)

    def test_matching_remote_account_is_adopted(self):
        mongo = MongoStub()
        osm = OsmStub()
        osm.addVim(
            "katana-link",
            "secret",
            "openstack",
            "https://openstack/v3",
            "katana",
            {},
            vimTenantName="katana-project",
        )
        ensure_link = self._ensure_link(mongo)

        _, action = ensure_link(
            {"id": "osm-main"},
            {
                "id": "core-openstack",
                "auth_url": "https://openstack/v3",
                "admin_project_name": "katana-project",
                "username": "katana",
                "password": "secret",
            },
            {"id": "osm-main", "account_name": "katana-link"},
            osm,
        )

        self.assertEqual(action, "adopted")

    def test_missing_managed_remote_account_is_recreated_without_deleting_others(self):
        unrelated = {
            "_id": "other-link",
            "nfvo_id": "osm-main",
            "vim_id": "other-openstack",
        }
        managed = {
            "_id": "managed-link",
            "nfvo_id": "osm-main",
            "vim_id": "core-openstack",
            "osm_vim_account_id": "missing-account",
            "config": {},
            "created_at": 1,
        }
        mongo = MongoStub({"nfvo_vim_links": [unrelated, managed]})
        osm = OsmStub()

        record, action = self._ensure_link(mongo)(
            {"id": "osm-main"},
            {
                "id": "core-openstack",
                "auth_url": "https://openstack/v3",
                "admin_project_name": "katana-project",
                "username": "katana",
                "password": "secret",
            },
            {"id": "osm-main", "account_name": "katana-link"},
            osm,
        )

        self.assertEqual(action, "created")
        self.assertEqual(record["_id"], "managed-link")
        self.assertIn(unrelated, mongo.collections["nfvo_vim_links"])

    def test_safe_link_configuration_change_updates_remote_account(self):
        mongo = MongoStub()
        osm = OsmStub()
        ensure_link = self._ensure_link(mongo)
        nfvo = {"id": "osm-main"}
        vim = {
            "id": "core-openstack",
            "auth_url": "https://openstack/v3",
            "admin_project_name": "katana-project",
            "username": "katana",
            "password": "secret",
        }
        ensure_link(
            nfvo,
            vim,
            {"id": "osm-main", "account_name": "katana-link", "config": {}},
            osm,
        )

        record, action = ensure_link(
            nfvo,
            vim,
            {
                "id": "osm-main",
                "account_name": "katana-link",
                "config": {"security_groups": "default"},
            },
            osm,
        )

        self.assertEqual(action, "updated")
        self.assertTrue(osm.updated)
        self.assertEqual(record["config"], {"security_groups": "default"})

    def test_remote_identity_drift_is_rejected(self):
        osm = OsmStub()
        osm.accounts["existing"] = {
            "_id": "existing",
            "name": "katana-link",
            "vim_type": "openstack",
            "vim_url": "https://openstack/v3",
            "vim_tenant_name": "different-project",
        }
        namespace = self._link_namespace(MongoStub())
        ensure_link = namespace["_ensure_link"]

        with self.assertRaises(namespace["BootstrapError"]) as raised:
            ensure_link(
                {"id": "osm-main"},
                {
                    "id": "core-openstack",
                    "auth_url": "https://openstack/v3",
                    "admin_project_name": "katana-project",
                    "username": "katana",
                    "password": "secret",
                },
                {"id": "osm-main", "account_name": "katana-link"},
                osm,
            )

        self.assertEqual(raised.exception.status_code, 409)


class ReconciliationRecoveryTests(unittest.TestCase):
    def test_partial_failure_is_recorded_and_rerun_succeeds(self):
        mongo = MongoStub()
        statuses = []
        calls = {"links": 0, "descriptors": 0}

        class ClientStub:
            def bootstrapNfvo(self):
                calls["descriptors"] += 1

        client = ClientStub()

        def acquire_lock(owner):
            mongo.add(
                "bootstrap_locks",
                {
                    "_id": "infrastructure-bootstrap",
                    "owner": owner,
                    "expires_at": time.time() + 60,
                },
            )

        def ensure_link(nfvo, vim, link, selected_client, credentials_changed):
            calls["links"] += 1
            if calls["links"] == 1:
                raise namespace["BootstrapError"]("temporary OSM failure", 502)
            return (
                {"nfvo_id": nfvo["id"], "vim_id": vim["id"]},
                "created",
            )

        namespace = load_definitions(
            "katana-nbi/katana/shared_utils/bootstrapUtils.py",
            {"BootstrapError", "reconcile_manifest"},
            {
                "validate_manifest": lambda value: value,
                "uuid": uuid,
                "time": time,
                "_acquire_lock": acquire_lock,
                "_ensure_nfvo": lambda data: (
                    {"id": data["id"]},
                    client,
                    "created",
                ),
                "_ensure_vim": lambda data: (
                    {"id": data["id"]},
                    "created",
                    True,
                ),
                "_ensure_link": ensure_link,
                "_store_status": statuses.append,
                "mongoUtils": mongo,
                "LOCK_ID": "infrastructure-bootstrap",
            },
        )

        with self.assertRaises(namespace["BootstrapError"]):
            namespace["reconcile_manifest"](manifest())

        result = namespace["reconcile_manifest"](manifest())

        self.assertEqual(statuses[0]["status"], "failed")
        self.assertEqual(statuses[-1]["status"], "succeeded")
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(calls["descriptors"], 1)
        self.assertFalse(mongo.collections.get("bootstrap_locks"))

    def test_reconciliation_processes_every_many_to_many_link(self):
        source = manifest()
        second_nfvo = copy.deepcopy(source["nfvos"][0])
        second_nfvo["id"] = "osm-backup"
        source["nfvos"].append(second_nfvo)
        source["vims"][0]["nfvos"].append({"id": "osm-backup"})
        second_vim = copy.deepcopy(source["vims"][0])
        second_vim["id"] = "edge-openstack"
        second_vim["location"] = "edge"
        second_vim["nfvos"] = [{"id": "osm-main"}, {"id": "osm-backup"}]
        source["vims"].append(second_vim)
        mongo = MongoStub()
        seen_links = []

        class ClientStub:
            @staticmethod
            def bootstrapNfvo():
                pass

        def acquire_lock(owner):
            mongo.add(
                "bootstrap_locks",
                {"_id": "infrastructure-bootstrap", "owner": owner},
            )

        def ensure_link(nfvo, vim, link, client, credentials_changed):
            seen_links.append((nfvo["id"], vim["id"]))
            return {"nfvo_id": nfvo["id"], "vim_id": vim["id"]}, "created"

        namespace = load_definitions(
            "katana-nbi/katana/shared_utils/bootstrapUtils.py",
            {"BootstrapError", "reconcile_manifest"},
            {
                "validate_manifest": lambda value: value,
                "uuid": uuid,
                "time": time,
                "_acquire_lock": acquire_lock,
                "_ensure_nfvo": lambda data: (
                    {"id": data["id"]},
                    ClientStub(),
                    "created",
                ),
                "_ensure_vim": lambda data: (
                    {"id": data["id"]},
                    "created",
                    True,
                ),
                "_ensure_link": ensure_link,
                "_store_status": lambda status: None,
                "mongoUtils": mongo,
                "LOCK_ID": "infrastructure-bootstrap",
            },
        )

        namespace["reconcile_manifest"](source)

        self.assertEqual(
            set(seen_links),
            {
                ("osm-main", "core-openstack"),
                ("osm-backup", "core-openstack"),
                ("osm-main", "edge-openstack"),
                ("osm-backup", "edge-openstack"),
            },
        )


class BootstrapLockTests(unittest.TestCase):
    def test_active_reconciliation_lock_returns_conflict(self):
        mongo = MongoStub(
            {
                "bootstrap_locks": [
                    {
                        "_id": "infrastructure-bootstrap",
                        "owner": "other",
                        "expires_at": time.time() + 60,
                    }
                ]
            }
        )
        namespace = load_definitions(
            "katana-nbi/katana/shared_utils/bootstrapUtils.py",
            {"BootstrapError", "_acquire_lock"},
            {
                "mongoUtils": mongo,
                "pymongo": PymongoStub,
                "time": time,
                "LOCK_ID": "infrastructure-bootstrap",
                "LOCK_SECONDS": 900,
            },
        )

        with self.assertRaises(namespace["BootstrapError"]) as raised:
            namespace["_acquire_lock"]("mine")
        self.assertEqual(raised.exception.status_code, 409)


class RedactionTests(unittest.TestCase):
    def test_public_record_removes_credentials(self):
        namespace = load_definitions(
            "katana-nbi/katana/shared_utils/bootstrapUtils.py",
            {"public_record"},
            {
                "REDACTED_FIELDS": {
                    "password",
                    "nfvopassword",
                    "credentials",
                    "obj",
                }
            },
        )
        result = namespace["public_record"](
            {
                "id": "osm-main",
                "nfvopassword": "secret",
                "obj": b"pickle",
                "config": {"password": "nested-secret", "region": "core"},
            }
        )
        self.assertEqual(result, {"id": "osm-main", "config": {"region": "core"}})


class SliceTargetValidationTests(unittest.TestCase):
    class UrllibStub:
        @staticmethod
        def disable_warnings():
            pass

    @staticmethod
    def route(*args, **kwargs):
        return lambda function: function

    def _view(self, collections):
        namespace = load_definitions(
            "katana-nbi/katana/api/slice.py",
            {"SliceView"},
            {
                "FlaskView": object,
                "route": self.route,
                "urllib3": self.UrllibStub,
                "mongoUtils": MongoStub(collections),
            },
        )
        return namespace["SliceView"]()

    @staticmethod
    def _payload():
        return {
            "service_descriptor": {
                "ns_list": [
                    {
                        "nsd-id": "nsd-1",
                        "ns-name": "frontend",
                        "nfvo-id": "osm-main",
                        "target": "core-openstack",
                        "placement": "core",
                    }
                ]
            }
        }

    @staticmethod
    def _collections(include_link=True):
        collections = {
            "nfvo": [{"id": "osm-main"}],
            "nsd": [
                {
                    "nsd-id": "nsd-1",
                    "nfvo_id": "osm-main",
                    "deployment_runtime": "openstack",
                }
            ],
            "vim": [
                {
                    "id": "core-openstack",
                    "type": "openstack",
                    "location": "core",
                }
            ],
        }
        if include_link:
            collections["nfvo_vim_links"] = [
                {"nfvo_id": "osm-main", "vim_id": "core-openstack"}
            ]
        return collections

    def test_valid_explicit_selection_is_accepted(self):
        runtime, error = self._view(self._collections())._validate_deployment_targets(
            self._payload()
        )
        self.assertEqual(runtime, "openstack")
        self.assertIsNone(error)

    def test_missing_target_is_rejected(self):
        payload = self._payload()
        del payload["service_descriptor"]["ns_list"][0]["target"]
        _, error = self._view(self._collections())._validate_deployment_targets(payload)
        self.assertIn("requires target", error[0])

    def test_unlinked_vim_is_rejected(self):
        _, error = self._view(
            self._collections(include_link=False)
        )._validate_deployment_targets(self._payload())
        self.assertIn("not linked", error[0])

    def test_slice_cannot_override_osm_account(self):
        payload = self._payload()
        payload["service_descriptor"]["ns_list"][0]["osm-vim-account-id"] = "manual"
        _, error = self._view(self._collections())._validate_deployment_targets(payload)
        self.assertIn("managed by Time-0 bootstrap", error[0])


if __name__ == "__main__":
    unittest.main()
