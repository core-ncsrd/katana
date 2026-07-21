import ast
import json
import os
import secrets
import time
from pathlib import Path
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]


def load_definitions(relative_path, names, globals_dict=None):
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ]
    namespace = dict(globals_dict or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class ClickStub:
    class ClickException(Exception):
        pass


class YamlStub:
    class YAMLError(Exception):
        pass

    @staticmethod
    def safe_load(stream):
        return json.load(stream)


class MongoStub:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def find(self, collection, query):
        for item in self.collections.get(collection, []):
            if all(item.get(key) == value for key, value in query.items()):
                return item
        return None

    def get(self, collection, item_id):
        return self.find(collection, {"_id": item_id})

    def find_all(self, collection, query=None):
        query = query or {}
        return [
            item
            for item in self.collections.get(collection, [])
            if all(item.get(key) == value for key, value in query.items())
        ]

    def add(self, collection, item):
        self.collections.setdefault(collection, []).append(item)
        return item.get("_id")

    def update(self, collection, item_id, item):
        values = self.collections.setdefault(collection, [])
        for index, current in enumerate(values):
            if current.get("_id") == item_id:
                values[index] = item
                return 1
        return 0

    def delete(self, collection, item_id):
        values = self.collections.setdefault(collection, [])
        self.collections[collection] = [
            current for current in values if current.get("_id") != item_id
        ]


class PymongoStub:
    class errors:
        class DuplicateKeyError(Exception):
            pass


class SliceConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = load_definitions(
            "katana-cli/cli/commands/cmd_slice.py",
            {"prepare_slice_data"},
            {"click": ClickStub, "yaml": YamlStub, "os": os},
        )
        cls.prepare = staticmethod(namespace["prepare_slice_data"])

    def test_existing_nest_is_unchanged(self):
        data = {"base_slice_descriptor": {}}
        self.assertIs(self.prepare(data, "/tmp/slice.yaml"), data)

    def test_inline_kubernetes_registration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "creds.json"
            credential_path.write_text(
                json.dumps({"clusters": [{}], "contexts": [{}], "users": [{}]})
            )
            data = {
                "infrastructure": {
                    "type": "kubernetes",
                    "credentials_file": "creds.json",
                }
            }
            with self.assertRaises(ClickStub.ClickException):
                self.prepare(data, str(Path(directory) / "slice.yaml"))

    def test_inline_openstack_registration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "clouds.json"
            credential_path.write_text(json.dumps({"clouds": {"one": {}, "two": {}}}))
            data = {
                "infrastructure": {
                    "type": "openstack",
                    "credentials_file": "clouds.json",
                }
            }
            with self.assertRaises(ClickStub.ClickException):
                self.prepare(data, str(Path(directory) / "slice.yaml"))


class AsyncSliceCreationTests(unittest.TestCase):
    def test_queued_record_is_immediately_readable(self):
        namespace = load_definitions(
            "katana-nbi/katana/api/slice.py",
            {"queued_slice_record"},
            {"time": time},
        )
        nest = {
            "_id": "slice-1",
            "slice_name": "frontend-test",
            "ns_list": [{"nsd-id": "nsd-1"}],
            "target_selection_version": "katana/v1",
        }

        record = namespace["queued_slice_record"](nest)

        self.assertEqual(record["status"], "Queued")
        self.assertEqual(record["slice_name"], "frontend-test")
        self.assertEqual(record["runtime_errors"], {})
        self.assertEqual(record["target_selection_version"], "katana/v1")
        self.assertIn("Placement_Time", record["deployment_time"])

    def test_manager_replaces_existing_queued_record(self):
        mongo = MongoStub(
            {"slice": [{"_id": "slice-1", "status": "Queued"}]}
        )
        namespace = load_definitions(
            "katana-mngr/katana/utils/sliceUtils/sliceUtils.py",
            {"_store_initial_slice_record"},
            {"mongoUtils": mongo},
        )
        initial = {
            "_id": "slice-1",
            "slice_name": "frontend-test",
            "status": "Init",
        }

        namespace["_store_initial_slice_record"](initial)

        self.assertEqual(mongo.collections["slice"], [initial])


class InfrastructureReuseTests(unittest.TestCase):
    def _check_existing(self, records):
        namespace = load_definitions(
            "katana-nbi/katana/shared_utils/infrastructureUtils.py",
            {"InfrastructureError", "_check_existing"},
            {"mongoUtils": MongoStub(records)},
        )
        return namespace["_check_existing"], namespace["InfrastructureError"]

    def test_matching_registration_is_reused(self):
        target = {
            "id": "edge-k8s",
            "type": "kubernetes",
            "location": "edge",
            "nfvo_id": "osm-1",
        }
        check, _ = self._check_existing({"k8sclusters": [target]})
        self.assertIs(check(dict(target)), target)

    def test_conflicting_registration_is_rejected(self):
        target = {
            "id": "edge-k8s",
            "type": "kubernetes",
            "location": "edge",
            "nfvo_id": "osm-1",
        }
        check, error_type = self._check_existing({"k8sclusters": [target]})
        conflicting = dict(target, nfvo_id="osm-2")
        with self.assertRaises(error_type) as raised:
            check(conflicting)
        self.assertEqual(raised.exception.status_code, 409)

    def test_missing_location_is_created(self):
        mongo = MongoStub()
        namespace = load_definitions(
            "katana-nbi/katana/shared_utils/infrastructureUtils.py",
            {"_ensure_location"},
            {"mongoUtils": mongo, "pymongo": PymongoStub, "time": time, "uuid": uuid},
        )
        location = namespace["_ensure_location"]("EDGE")
        self.assertEqual(location["id"], "edge")
        self.assertEqual(mongo.collections["location"][0]["id"], "edge")

    def test_kubernetes_credentials_are_not_persisted(self):
        class OsmStub:
            def getToken(self):
                return "token"

            def addVim(self, *args):
                return "vim-account"

            def addK8sCluster(self, payload):
                return {"id": "osm-cluster"}

        class PickleStub:
            @staticmethod
            def loads(value):
                return OsmStub()

        mongo = MongoStub(
            {
                "nfvo": [{"_id": "nfvo-db", "id": "osm-1"}],
                "nfvo_obj": [{"_id": "obj-db", "id": "osm-1", "obj": b"ignored"}],
            }
        )
        namespace = load_definitions(
            "katana-nbi/katana/shared_utils/infrastructureUtils.py",
            {"InfrastructureError", "_add_location_target", "_register_kubernetes"},
            {
                "mongoUtils": mongo,
                "pickle": PickleStub,
                "pymongo": PymongoStub,
                "time": time,
                "uuid": uuid,
            },
        )
        record = namespace["_register_kubernetes"](
            {
                "id": "edge-k8s",
                "location": "edge",
                "nfvo_id": "osm-1",
                "k8s_version": "v1.30",
                "credentials": {"clusters": [{}], "contexts": [{}], "users": [{}]},
            },
            {"_id": "location-db", "id": "edge", "vims": []},
        )
        self.assertNotIn("credentials", record)
        self.assertNotIn("credentials", mongo.collections["k8sclusters"][0])


class DescriptorClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = load_definitions(
            "katana-mngr/katana/shared_utils/nfvoUtils/osmUtils.py",
            {"classify_workload_descriptor"},
        )
        cls.classify = staticmethod(namespace["classify_workload_descriptor"])

    def test_descriptor_runtimes(self):
        self.assertEqual(self.classify({"vdu": [{}]}), "openstack")
        self.assertEqual(self.classify({"kdu": [{}]}), "kubernetes")
        self.assertEqual(self.classify({"vdu": [{}], "kdu": [{}]}), "mixed")
        self.assertEqual(self.classify({}), "unknown")


class OsmAuthenticationRetryTests(unittest.TestCase):
    class LoggerStub:
        def warning(self, *args):
            pass

    class TimeStub:
        @staticmethod
        def sleep(seconds):
            pass

    class ResponseStub:
        def __init__(self, data=None, status_code=200):
            self.data = data
            self.status_code = status_code
            self.content = b"{}" if data is not None else b""

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    class RequestsStub:
        class RequestException(Exception):
            pass

        class Timeout(RequestException):
            pass

        def __init__(self, outcomes):
            self.outcomes = list(outcomes)
            self.calls = 0
            self.call_kwargs = []

        def _request(self, *args, **kwargs):
            self.call_kwargs.append(kwargs)
            outcome = self.outcomes[self.calls]
            self.calls += 1
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        post = _request
        get = _request
        patch = _request

    def _osm(self, outcomes):
        requests_stub = self.RequestsStub(outcomes)
        namespace = load_definitions(
            "katana-mngr/katana/shared_utils/nfvoUtils/osmUtils.py",
            {"OsmAuthenticationError", "OsmRequestError", "Osm"},
            {
                "requests": requests_stub,
                "time": self.TimeStub,
                "logger": self.LoggerStub(),
                "OSM_REQUEST_ATTEMPTS": 3,
                "OSM_AUTH_TIMEOUT": 20,
                "OSM_WRITE_TIMEOUT": 30,
            },
        )
        return (
            namespace["Osm"]("osm-1", "osm.example", "user", "password"),
            requests_stub,
            namespace["OsmAuthenticationError"],
            namespace["OsmRequestError"],
        )

    def test_authentication_retries_then_succeeds(self):
        failure = self.RequestsStub.RequestException("timeout")
        osm, requests_stub, _, _ = self._osm(
            [failure, failure, self.ResponseStub({"id": "token"})]
        )

        self.assertEqual(osm.getToken(), "token")
        self.assertEqual(requests_stub.calls, 3)
        self.assertTrue(
            all(call["timeout"] == 20 for call in requests_stub.call_kwargs)
        )
        self.assertEqual(
            requests_stub.call_kwargs[-1]["json"],
            {"username": "user", "password": "password", "project_id": "admin"},
        )

    def test_authentication_failure_is_explicit_after_three_attempts(self):
        failures = [
            self.RequestsStub.RequestException("timeout") for _ in range(3)
        ]
        osm, requests_stub, error_type, _ = self._osm(failures)

        with self.assertRaises(error_type) as raised:
            osm.getToken()

        self.assertEqual(requests_stub.calls, 3)
        self.assertEqual(
            str(raised.exception), "OSM authentication failed after 3 attempts"
        )

    def test_vim_registration_reauthenticates_after_unauthorized_response(self):
        failure = self.RequestsStub.RequestException("timeout")
        osm, requests_stub, _, _ = self._osm(
            [
                self.ResponseStub(status_code=401),
                failure,
                self.ResponseStub({"id": "token"}),
                self.ResponseStub({"id": "vim-account"}),
            ]
        )
        osm.token = "stale-token"

        self.assertEqual(
            osm.addVim("name", "password", "openstack", "url", "user", {}),
            "vim-account",
        )
        self.assertEqual(requests_stub.calls, 4)
        self.assertEqual(requests_stub.call_kwargs[-1]["timeout"], 30)

    def test_vim_registration_timeout_is_explicit(self):
        osm, _, _, error_type = self._osm(
            [self.RequestsStub.Timeout("timeout")]
        )
        osm.token = "token"

        with self.assertRaises(error_type) as raised:
            osm.addVim("name", "password", "openstack", "url", "user", {})

        self.assertEqual(
            str(raised.exception),
            "OSM VIM registration timed out after 30 seconds",
        )

    def test_vim_registration_uses_distinct_account_and_tenant_names(self):
        osm, requests_stub, _, _ = self._osm(
            [self.ResponseStub({"id": "vim-account"})]
        )
        osm.token = "token"

        osm.addVim(
            "katana-link",
            "secret",
            "openstack",
            "https://openstack/v3",
            "katana",
            {"security_groups": "default"},
            vimTenantName="katana-project",
        )

        payload = requests_stub.call_kwargs[-1]["json"]
        self.assertEqual(payload["name"], "katana-link")
        self.assertEqual(payload["vim_tenant_name"], "katana-project")
        self.assertTrue(requests_stub.call_kwargs[-1]["verify"])

    def test_vim_list_get_and_patch_use_structured_requests(self):
        account = {"_id": "vim-account", "name": "katana-link"}
        osm, requests_stub, _, _ = self._osm(
            [
                self.ResponseStub([account]),
                self.ResponseStub(account),
                self.ResponseStub({}),
            ]
        )
        osm.token = "token"

        self.assertEqual(osm.listVims(), [account])
        self.assertEqual(osm.getVim("vim-account"), account)
        osm.updateVim(
            "vim-account",
            vim_user="katana",
            vim_password="secret",
            config={"security_groups": "default"},
        )

        self.assertEqual(
            requests_stub.call_kwargs[-1]["json"],
            {
                "vim_user": "katana",
                "vim_password": "secret",
                "config": {"security_groups": "default"},
            },
        )
        self.assertTrue(
            all(call["verify"] for call in requests_stub.call_kwargs)
        )

    def test_vim_readiness_failure_is_explicit(self):
        osm, _, _, error_type = self._osm([])
        osm.getVim = lambda vim_id: {
            "_id": vim_id,
            "_admin": {
                "operationalState": "FAILED",
                "detailed-status": "authentication rejected",
            },
        }

        with self.assertRaises(error_type) as raised:
            osm.waitForVim("vim-account", attempts=1, interval=0)

        self.assertIn("authentication rejected", str(raised.exception))

    def test_vim_readiness_timeout_is_bounded(self):
        osm, _, _, error_type = self._osm([])
        osm.getVim = lambda vim_id: {
            "_id": vim_id,
            "_admin": {"operationalState": "PROCESSING"},
        }

        with self.assertRaises(error_type) as raised:
            osm.waitForVim("vim-account", attempts=2, interval=0)

        self.assertIn("did not become ready", str(raised.exception))


class SliceFailureTests(unittest.TestCase):
    class LoggerStub:
        def error(self, *args):
            pass

    def test_osm_failure_is_persisted(self):
        mongo = MongoStub({"slice": [{"_id": "slice-1"}]})
        namespace = load_definitions(
            "katana-mngr/katana/utils/sliceUtils/sliceUtils.py",
            {"fail_slice"},
            {"mongoUtils": mongo, "logger": self.LoggerStub()},
        )
        nest = {"_id": "slice-1", "status": "Provisioning"}

        namespace["fail_slice"](
            nest, "OSM authentication failed after 3 attempts"
        )

        self.assertEqual(
            nest["status"], "Failed - OSM authentication failed after 3 attempts"
        )
        self.assertEqual(
            nest["runtime_errors"]["deployment"],
            ["OSM authentication failed after 3 attempts"],
        )


class OpenStackTenantCredentialTests(unittest.TestCase):
    def test_openstack_constructor_honors_tls_verification(self):
        captured = {}

        class ConnectionStub:
            @staticmethod
            def authorize():
                return None

        class OpenstackModuleStub:
            @staticmethod
            def connect(**kwargs):
                captured.update(kwargs)
                return ConnectionStub()

        namespace = load_definitions(
            "katana-mngr/katana/shared_utils/vimUtils/openstackUtils.py",
            {"timeout", "Openstack"},
            {
                "functools": __import__("functools"),
                "Process": object,
                "openstack": OpenstackModuleStub,
            },
        )

        namespace["Openstack"](
            "vim-1",
            "https://openstack/v3",
            "project",
            "user",
            "secret",
            verify="/bootstrap/ca.pem",
        )

        self.assertEqual(captured["verify"], "/bootstrap/ca.pem")

    def test_slice_credentials_are_unique_and_not_hardcoded(self):
        namespace = load_definitions(
            "katana-mngr/katana/utils/sliceUtils/sliceUtils.py",
            {"slice_tenant_credentials", "openstack_vim_config"},
            {"secrets": secrets},
        )

        first = namespace["slice_tenant_credentials"]("slice-project")
        second = namespace["slice_tenant_credentials"]("slice-project")

        self.assertEqual(first[0], "slice-project")
        self.assertNotEqual(first[1], "password")
        self.assertNotEqual(first[1], second[1])
        self.assertEqual(
            namespace["openstack_vim_config"]("slice-security-group"),
            {
                "security_groups": "slice-security-group",
                "user_domain_id": "default",
                "project_domain_id": "default",
            },
        )

    def test_openstack_user_receives_supplied_password(self):
        class OpenstackModuleStub:
            @staticmethod
            def connect(**kwargs):
                return object()

        namespace = load_definitions(
            "katana-mngr/katana/shared_utils/vimUtils/openstackUtils.py",
            {"timeout", "Openstack"},
            {
                "functools": __import__("functools"),
                "Process": object,
                "openstack": OpenstackModuleStub,
            },
        )
        simple_namespace = __import__("types").SimpleNamespace
        target = namespace["Openstack"].__new__(namespace["Openstack"])
        target.auth_url = "http://openstack/v3"
        target.project_name = "admin"
        target.username = "admin"
        target.password = "admin-secret"
        target.user_domain_name = "Default"
        target.project_domain_name = "default"
        target.verify = False
        target.openstack_authorize = lambda conn: None
        target.create_project = lambda conn, name, description: simple_namespace(
            name=name
        )
        captured = {}

        def create_user(conn, name, password):
            captured["password"] = password
            return simple_namespace(name=name)

        target.create_user = create_user
        target.combine_proj_user = lambda *args: None
        target.create_sec_group = lambda conn, name, project: simple_namespace(
            name=name
        )
        target.set_quotas = lambda *args: None

        target.create_slice_prerequisites(
            "slice-project",
            "description",
            "slice-user",
            "generated-secret",
            "slice-id",
        )

        self.assertEqual(captured["password"], "generated-secret")

    def test_current_member_role_is_assigned_without_legacy_heat_role(self):
        class OpenstackModuleStub:
            pass

        namespace = load_definitions(
            "katana-mngr/katana/shared_utils/vimUtils/openstackUtils.py",
            {"find_first_role", "timeout", "Openstack"},
            {
                "functools": __import__("functools"),
                "Process": object,
                "openstack": OpenstackModuleStub,
            },
        )
        simple_namespace = __import__("types").SimpleNamespace
        member_role = simple_namespace(name="member")
        admin_role = simple_namespace(name="admin")
        admin_user = simple_namespace(name="admin")
        assignments = []

        class IdentityStub:
            @staticmethod
            def find_role(name):
                return {"member": member_role, "admin": admin_role}.get(name)

            @staticmethod
            def find_user(name, ignore_missing=False):
                return admin_user

            @staticmethod
            def assign_project_role_to_user(project, user, role):
                assignments.append((user.name, role.name))

        target = namespace["Openstack"].__new__(namespace["Openstack"])
        target.combine_proj_user(
            simple_namespace(identity=IdentityStub()),
            simple_namespace(name="slice-project"),
            simple_namespace(name="slice-user"),
            "admin",
        )

        self.assertEqual(
            assignments,
            [("slice-user", "member"), ("admin", "admin")],
        )


class TargetResolutionTests(unittest.TestCase):
    def _resolver(self, collections):
        namespace = load_definitions(
            "katana-mngr/katana/utils/sliceUtils/sliceUtils.py",
            {
                "_deployment_target",
                "_requested_nfvo_id",
                "nfvo_vim_link",
                "resolve_deployment_target",
            },
            {"mongoUtils": MongoStub(collections)},
        )
        return namespace["resolve_deployment_target"]

    def _ns(self, runtime="kubernetes"):
        return {
            "nsd-info": {"deployment_runtime": runtime, "nfvo_id": "osm-1"},
            "nfvo-id": "osm-1",
            "target": "edge-k8s",
        }

    def test_explicit_compatible_target_is_selected(self):
        target = {
            "id": "edge-k8s",
            "type": "kubernetes",
            "location": "edge",
            "nfvo_id": "osm-1",
        }
        selected, error = self._resolver({"k8sclusters": [target]})(self._ns(), "edge")
        self.assertIs(selected, target)
        self.assertIsNone(error)

    def test_missing_explicit_target_fails(self):
        ns = self._ns()
        del ns["target"]
        selected, error = self._resolver({})(ns, "edge")
        self.assertIsNone(selected)
        self.assertIn("requires target", error)

    def test_missing_target_fails_explicitly(self):
        selected, error = self._resolver({})(self._ns(), "edge")
        self.assertIsNone(selected)
        self.assertIn("edge-k8s not found", error)

    def test_preferred_target_does_not_override_explicit_target(self):
        targets = [
            {"id": name, "type": "kubernetes", "location": "edge", "nfvo_id": "osm-1"}
            for name in ("one", "two")
        ]
        ns = self._ns()
        ns["target"] = "one"
        selected, error = self._resolver({"k8sclusters": targets})(
            ns, "edge", preferred_target_id="two"
        )
        self.assertEqual(selected["id"], "one")
        self.assertIsNone(error)

    def test_explicit_nfvo_overrides_mutable_nsd_owner(self):
        target = {
            "id": "core-openstack",
            "type": "openstack",
            "location": "core",
            "nfvo_id": "osm-selected",
        }
        ns = self._ns(runtime="openstack")
        ns["nfvo-id"] = "osm-selected"
        ns["target"] = "core-openstack"

        selected, error = self._resolver(
            {
                "vim": [target],
                "nfvo_vim_links": [
                    {"nfvo_id": "osm-selected", "vim_id": "core-openstack"}
                ],
            }
        )(ns, "core")

        self.assertIs(selected, target)
        self.assertIsNone(error)


class TimeZeroOsmVimAccountTests(unittest.TestCase):
    class LoggerStub:
        def error(self, *args):
            pass

    def test_bootstrapped_account_is_marked_persistent_for_provisioning(self):
        nsd = {
            "nsd-id": "nsd-1",
            "nfvo_id": "osm-bootstrap-owner",
            "deployment_runtime": "openstack",
            "flavor": {
                "memory-mb": 1,
                "vcpu-count": 1,
                "storage-gb": 1,
                "instances": 1,
            },
        }
        target = {
            "id": "core-openstack",
            "type": "openstack",
            "location": "core",
        }
        namespace = load_definitions(
            "katana-mngr/katana/utils/sliceUtils/sliceUtils.py",
            {
                "_deployment_target",
                "_requested_nfvo_id",
                "nfvo_vim_link",
                "persistent_vim_account",
                "resolve_deployment_target",
                "ns_details",
            },
            {
                "mongoUtils": MongoStub(
                    {
                        "nsd": [nsd],
                        "vim": [target],
                        "nfvo_vim_links": [
                            {
                                "nfvo_id": "osm-selected",
                                "vim_id": "core-openstack",
                                "osm_vim_account_id": "account-1",
                            }
                        ],
                    }
                ),
                "copy": __import__("copy"),
                "uuid": uuid,
                "logger": self.LoggerStub(),
            },
        )
        vim_dict = {}
        total_ns_list = []

        error, _ = namespace["ns_details"](
            [
                {
                    "nsd-id": "nsd-1",
                    "ns-name": "new-ns",
                    "placement": "core",
                    "target": "core-openstack",
                    "nfvo-id": "osm-selected",
                }
            ],
            "core",
            vim_dict,
            total_ns_list,
        )

        self.assertEqual(error, 0)
        self.assertTrue(vim_dict["core-openstack"]["persistent_nfvo_vim_account"])
        self.assertEqual(
            vim_dict["core-openstack"]["nfvo_vim_account"],
            {"osm-selected": "account-1"},
        )
        self.assertEqual(total_ns_list[0]["nfvo-id"], "osm-selected")


if __name__ == "__main__":
    unittest.main()
