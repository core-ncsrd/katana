import logging
import os
import re
import time
from logging import handlers
from collections import deque
import uuid

from bson.json_util import dumps
from flask import request
from flask_classful import FlaskView, route
import requests
import urllib3

from katana.shared_utils.kafkaUtils import kafkaUtils
from katana.shared_utils.mongoUtils import mongoUtils
from katana.slice_mapping import slice_mapping

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

SLICE_STATUS = {
    0: "Running",
    1: "Placement",
    2: "Provisioning",
    3: "Activation",
    10: "Terminating",
    11: "Error",
    12: "Deleted",
}

NS_STATUS = {
    1: "Starting",
    2: "Missing",
    3: "Not running",
    4: "Terminating",
    5: "Admin stopped",
}

VM_PANELS = [
    "vm_state",
    "vm_cpu_cpu_time",
    "vm_cpu_overall_cpu_usage",
    "vm_memory_actual",
    "vm_memory_available",
    "vm_memory_usage",
    "vm_disk_read_bytes",
    "vm_disk_write_bytes",
    "vm_disk_errors",
]


def queued_slice_record(nest):
    """Create the immediately readable record returned by asynchronous creation."""
    record = dict(nest)
    record.update(
        {
            "status": "Queued",
            "created_at": time.time(),
            "runtime_errors": {},
            "deployment_time": {
                "Placement_Time": None,
                "Provisioning_Time": None,
                "WAN_Deployment_Time": None,
                "NS_Deployment_Time": None,
                "Radio_Configuration_Time": None,
                "Slice_Deployment_Time": None,
            },
        }
    )
    return record


class SliceView(FlaskView):
    """
    Returns a list of slices and their details,
    used by: `katana slice ls`
    """

    urllib3.disable_warnings()
    route_prefix = "/api/"

    def _public_service_url(self, env_name, default_port):
        configured = os.getenv(env_name)
        if configured:
            return configured.rstrip("/")

        host = request.host.split(":", 1)[0]
        return f"{request.scheme}://{host}:{default_port}"

    def _prometheus_url(self):
        return os.getenv("KATANA_PROMETHEUS_URL", "http://katana-prometheus:9090").rstrip("/")

    def _slice_name(self, islice):
        return islice.get("slice_name") or islice.get("name") or islice["_id"]

    def _slice_prometheus_queries(self, islice, include_infrastructure=False):
        slice_id = islice["_id"]
        metric_slice_id = "slice_" + slice_id.replace("-", "_")
        queries = {
            "slice_status": f'katana_status{{slice_id="{slice_id}"}}',
            "network_services": f'ns_status{{slice_id="{slice_id}"}}',
        }

        if islice.get("slice_monitoring", {}).get("WIM"):
            queries["wim_flows_per_second"] = f"rate({metric_slice_id}_flows[1m])"

        if include_infrastructure:
            queries.update(self._slice_vm_prometheus_queries(islice))
        return queries

    def _slice_vm_prometheus_queries(self, islice):
        queries = {}
        for vim_type, vm_list in self._slice_vm_targets(islice).items():
            for panel in VM_PANELS:
                key = f"{vim_type}_{panel}"
                selectors = [
                    f'project=~".*{islice["_id"]}"',
                    f'vm_name=~"{self._prometheus_regex(vm_list)}"',
                ]
                queries[key] = f"{vim_type}_{panel}" + "{" + ",".join(selectors) + "}"
        return queries

    def _slice_vm_targets(self, islice):
        targets = {}
        for ns in (islice.get("ns_inst_info") or {}).values():
            for value in ns.values():
                vim_id = value.get("vim")
                if not vim_id:
                    continue
                search_vim_id = vim_id[:-2] if value.get("shared", False) else vim_id
                selected_vim = mongoUtils.find("vim", {"id": search_vim_id})
                if not selected_vim:
                    continue
                vm_list = targets.get(selected_vim["type"], [])
                for vnfr in value.get("vnfr") or []:
                    vm_list.extend(vnfr.get("vm_list") or [])
                if vm_list:
                    targets[selected_vim["type"]] = sorted(set(vm_list))
        return targets

    def _prometheus_regex(self, values):
        return "|".join(re.escape(str(value)).replace('"', '\\"') for value in values)

    def _query_prometheus(self, queries):
        results = {}
        prometheus_url = self._prometheus_url()
        for name, query in queries.items():
            try:
                response = requests.get(
                    f"{prometheus_url}/api/v1/query",
                    params={"query": query},
                    timeout=2,
                )
                response.raise_for_status()
                results[name] = response.json()
            except Exception as exc:
                results[name] = {"status": "unavailable", "error": str(exc)}
        return results

    def _query_prometheus_range(self, query, start, end, step):
        try:
            response = requests.get(
                f"{self._prometheus_url()}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": step},
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            return {"status": "unavailable", "error": str(exc)}

    def _metric_value(self, result):
        try:
            return float(result["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def _metric_timestamp(self, result):
        try:
            return result["value"][0]
        except (KeyError, IndexError, TypeError):
            return None

    def _prometheus_vector(self, result):
        if result.get("status") != "success":
            return []
        return result.get("data", {}).get("result") or []

    def _status_label(self, status_map, value):
        if value is None:
            return "Unknown"
        try:
            return status_map.get(int(value), "Unknown")
        except (TypeError, ValueError):
            return "Unknown"

    def _monitoring_summary_payload(self, islice):
        queries = (
            self._slice_prometheus_queries(islice, include_infrastructure=True)
            if "slice_monitoring" in islice
            else {}
        )
        results = self._query_prometheus(queries) if queries else {}
        slice_status = None
        network_services = []
        infrastructure = {}

        for result in self._prometheus_vector(results.get("slice_status", {})):
            value = self._metric_value(result)
            slice_status = {
                "value": value,
                "label": self._status_label(SLICE_STATUS, value),
                "timestamp": self._metric_timestamp(result),
                "labels": result.get("metric", {}),
            }

        for result in self._prometheus_vector(results.get("network_services", {})):
            value = self._metric_value(result)
            network_services.append(
                {
                    "name": result.get("metric", {}).get("ns_name"),
                    "value": value,
                    "label": self._status_label(NS_STATUS, value),
                    "timestamp": self._metric_timestamp(result),
                    "labels": result.get("metric", {}),
                }
            )

        for name, result in results.items():
            if name in ("slice_status", "network_services", "wim_flows_per_second"):
                continue
            infrastructure[name] = [
                {
                    "vm_name": item.get("metric", {}).get("vm_name"),
                    "value": self._metric_value(item),
                    "timestamp": self._metric_timestamp(item),
                    "labels": item.get("metric", {}),
                }
                for item in self._prometheus_vector(result)
            ]

        return {
            "_id": islice["_id"],
            "name": self._slice_name(islice),
            "status": islice.get("status"),
            "monitoring": {
                "configured": "slice_monitoring" in islice,
                "details": islice.get("slice_monitoring") or {},
                "prometheus": {
                    "base_url": self._public_service_url("KATANA_PUBLIC_PROMETHEUS_URL", 9090),
                    "queries": queries,
                    "unavailable": {
                        name: result
                        for name, result in results.items()
                        if result.get("status") != "success"
                    },
                },
            },
            "metrics": {
                "slice_status": slice_status,
                "network_services": network_services,
                "wim_flows_per_second": self._prometheus_vector(results.get("wim_flows_per_second", {})),
                "infrastructure": infrastructure,
            },
        }

    def _slice_observability_payload(self, islice, include_prometheus=False):
        monitoring = islice.get("slice_monitoring") or {}
        monitoring_configured = "slice_monitoring" in islice
        dashboard_available = bool(monitoring)
        dashboard_uid = islice["_id"] if dashboard_available else None
        grafana_url = self._public_service_url("KATANA_PUBLIC_GRAFANA_URL", 3000)
        prometheus_public_url = self._public_service_url("KATANA_PUBLIC_PROMETHEUS_URL", 9090)
        queries = self._slice_prometheus_queries(islice) if monitoring_configured else {}

        payload = {
            "_id": islice["_id"],
            "name": self._slice_name(islice),
            "status": islice.get("status"),
            "created_at": islice.get("created_at"),
            "monitoring": {
                "configured": monitoring_configured,
                "dashboard_available": dashboard_available,
                "details": monitoring,
                "grafana": {
                    "dashboard_uid": dashboard_uid,
                    "dashboard_url": f"{grafana_url}/d/{dashboard_uid}" if dashboard_uid else None,
                },
                "prometheus": {
                    "base_url": prometheus_public_url,
                    "queries": queries,
                },
            },
            "links": {
                "details": f"/api/slice/{islice['_id']}",
                "logs": f"/api/slice/{islice['_id']}/logs",
                "monitoring": f"/api/slice/{islice['_id']}/monitoring",
                "monitoring_summary": f"/api/slice/{islice['_id']}/monitoring/summary",
                "monitoring_range": f"/api/slice/{islice['_id']}/monitoring/range",
                "alerts": f"/api/slice/{islice['_id']}/alerts",
                "errors": f"/api/slice/{islice['_id']}/errors",
                "deployment_time": f"/api/slice/{islice['_id']}/time",
            },
        }

        if include_prometheus and queries:
            payload["monitoring"]["prometheus"]["results"] = self._query_prometheus(queries)

        return payload

    def _slice_state_events(self, islice):
        events = [
            {
                "source": "slice-record",
                "level": "info",
                "timestamp": islice.get("created_at"),
                "message": "Slice created",
                "slice_id": islice["_id"],
            }
        ]

        for step, duration in (islice.get("deployment_time") or {}).items():
            if duration is None:
                continue
            events.append(
                {
                    "source": "slice-record",
                    "level": "info",
                    "timestamp": None,
                    "message": f"{step} completed in {duration} seconds",
                    "slice_id": islice["_id"],
                }
            )

        for ns_id, locations in (islice.get("ns_inst_info") or {}).items():
            for location, info in locations.items():
                status = info.get("status")
                if not status:
                    continue
                events.append(
                    {
                        "source": "slice-record",
                        "level": "info",
                        "timestamp": None,
                        "message": f"Network service {ns_id} at {location} is {status}",
                        "slice_id": islice["_id"],
                    }
                )

        runtime_errors = islice.get("runtime_errors") or {}
        for key, value in runtime_errors.items():
            events.append(
                {
                    "source": "slice-record",
                    "level": "error",
                    "timestamp": None,
                    "message": f"Runtime error in {key}: {value}",
                    "slice_id": islice["_id"],
                }
            )

        events.append(
            {
                "source": "slice-record",
                "level": "info",
                "timestamp": None,
                "message": f"Current slice status: {islice.get('status')}",
                "slice_id": islice["_id"],
            }
        )
        return events

    def _slice_alerts(self, slice_id, limit):
        alerts = list(mongoUtils.find_all("alerts", {"slice_id": slice_id}))
        alerts.sort(key=lambda alert: alert.get("received_at", 0), reverse=True)
        return alerts[:limit]

    def _slice_alert_events(self, slice_id, limit):
        events = []
        for alert in self._slice_alerts(slice_id, limit):
            alert_name = alert.get("alertname") or alert.get("labels", {}).get("alertname")
            status = alert.get("status") or "unknown"
            ns_name = alert.get("labels", {}).get("ns_name")
            message = f"Alert {alert_name} is {status}"
            if ns_name:
                message = f"{message} for {ns_name}"
            events.append(
                {
                    "source": "alertmanager",
                    "level": "warning" if status == "firing" else "info",
                    "timestamp": alert.get("received_at"),
                    "timestamp_iso": alert.get("received_at_iso"),
                    "message": message,
                    "slice_id": slice_id,
                    "alert": alert,
                }
            )
        return events

    def _local_slice_log_lines(self, slice_id, limit):
        paths = ["katana.log"]
        paths.extend(f"katana.log.{index}" for index in range(5, 0, -1))
        lines = deque(maxlen=limit)

        for path in paths:
            if not os.path.exists(path):
                continue
            try:
                with open(path, mode="r", encoding="utf-8", errors="replace") as log_file:
                    for line in log_file:
                        if slice_id in line:
                            lines.append(
                                {
                                    "source": path,
                                    "message": line.rstrip(),
                                    "slice_id": slice_id,
                                }
                            )
            except OSError as exc:
                lines.append(
                    {
                        "source": path,
                        "level": "warning",
                        "message": f"Could not read log file: {exc}",
                        "slice_id": slice_id,
                    }
                )

        return list(lines)

    def _request_limit(self, default=100, maximum=500):
        try:
            limit = int(request.args.get("limit", default))
        except (TypeError, ValueError):
            limit = default
        return max(1, min(limit, maximum))

    def _range_window(self):
        now = time.time()
        default_start = now - 3600
        try:
            start = float(request.args.get("start", default_start))
        except (TypeError, ValueError):
            start = default_start
        try:
            end = float(request.args.get("end", now))
        except (TypeError, ValueError):
            end = now
        if end <= start:
            end = start + 3600
        return start, end, request.args.get("step", "30s")

    def _validate_slice_payload(self, data):
        if not isinstance(data, dict):
            return "Error: Request body must be a JSON object", 400

        base_slice_descriptor = data.get("base_slice_descriptor")
        if base_slice_descriptor is None:
            return "Error: Required field base_slice_descriptor is missing", 400
        if not isinstance(base_slice_descriptor, dict):
            return "Error: Field 'base_slice_descriptor' must be a JSON object", 400

        for field in ("service_descriptor", "test_descriptor"):
            if data.get(field) is not None and not isinstance(data[field], dict):
                return f"Error: Field '{field}' must be a JSON object", 400

        return None

    def _validate_deployment_targets(self, data):
        service_descriptor = data.get("service_descriptor") or {}
        ns_list = service_descriptor.get("ns_list") or []
        if not ns_list:
            return None, ("Error: service_descriptor.ns_list is required", 400)

        runtimes = set()
        for ns in ns_list:
            if not isinstance(ns, dict) or not ns.get("nsd-id"):
                return None, ("Error: Every network service requires nsd-id", 400)
            if not ns.get("nfvo-id"):
                return None, ("Error: Every network service requires nfvo-id", 400)
            if not ns.get("target"):
                return None, ("Error: Every network service requires target", 400)
            if ns.get("osm-vim-account-id") is not None or ns.get("osm_vim_account_id") is not None:
                return None, (
                    "Error: osm-vim-account-id is managed by Time-0 bootstrap and cannot be supplied by a slice",
                    400,
                )
            nsd = mongoUtils.find("nsd", {"nsd-id": ns["nsd-id"]})
            if not nsd:
                return None, (f"Error: NSD {ns['nsd-id']} is not registered", 400)
            runtime = nsd.get("deployment_runtime")
            nfvo_id = ns["nfvo-id"]
            if not mongoUtils.find("nfvo", {"id": nfvo_id}):
                return None, (
                    f"Error: NFVO {nfvo_id} is not registered",
                    400,
                )
            if nsd.get("nfvo_id") != nfvo_id:
                return None, (
                    f"Error: NFVO {nfvo_id} does not own NSD {ns['nsd-id']}",
                    400,
                )
            if runtime in ("mixed", "unknown"):
                return None, (
                    f"Error: NSD {ns['nsd-id']} has unsupported {runtime} deployment runtime",
                    400,
                )
            target = mongoUtils.find("vim", {"id": ns["target"]})
            if not target:
                target = mongoUtils.find("k8sclusters", {"id": ns["target"]})
            if not target:
                return None, (f"Error: Infrastructure {ns['target']} is not registered", 400)
            if runtime and target.get("type", "").lower() != runtime:
                return None, (
                    f"Error: Infrastructure {ns['target']} does not support {runtime}",
                    400,
                )
            placement = str(ns.get("placement", "")).lower()
            if placement and target.get("location") != placement:
                return None, (
                    f"Error: Infrastructure {ns['target']} is not in location {placement}",
                    400,
                )
            if target.get("type", "").lower() == "openstack" and not mongoUtils.find(
                "nfvo_vim_links", {"nfvo_id": nfvo_id, "vim_id": target["id"]}
            ):
                return None, (
                    f"Error: Infrastructure {target['id']} is not linked to NFVO {nfvo_id}",
                    400,
                )
            if target.get("type", "").lower() == "kubernetes" and target.get("nfvo_id") != nfvo_id:
                return None, (
                    f"Error: Kubernetes infrastructure {target['id']} is not linked to NFVO {nfvo_id}",
                    400,
                )
            if runtime:
                runtimes.add(runtime)

        if len(runtimes) > 1:
            return None, ("Error: A slice cannot mix OpenStack and Kubernetes services", 400)
        if not runtimes:
            return None, ("Error: Unable to determine the NSD deployment runtime", 400)
        return next(iter(runtimes), None), None

    def _validate_modify_payload(self, islice, updates):
        if not isinstance(updates, dict) or not isinstance(updates.get("details"), dict):
            return "Error: Slice modification requires a details object", 400
        details = updates["details"]
        if updates.get("action") == "AddNS":
            required = ("nsd_id", "ns_name", "location", "nfvo_id", "target")
            missing = [field for field in required if not details.get(field)]
            if missing:
                return f"Error: AddNS is missing: {', '.join(missing)}", 400
            _, error = self._validate_deployment_targets(
                {
                    "service_descriptor": {
                        "ns_list": [
                            {
                                "nsd-id": details["nsd_id"],
                                "ns-name": details["ns_name"],
                                "placement": details["location"],
                                "nfvo-id": details["nfvo_id"],
                                "target": details["target"],
                            }
                        ]
                    }
                }
            )
            return error
        if updates.get("action") == "RestartNS" and details.get("change_vim"):
            target_id = details.get("target")
            if not target_id:
                return "Error: RestartNS requires target when change_vim is true", 400
            try:
                current = islice["ns_inst_info"][details["ns_id"]][details["location"]]
            except KeyError:
                return "Error: Network service instance was not found", 404
            target = mongoUtils.find("vim", {"id": target_id})
            if not target or target.get("location") != details["location"]:
                return f"Error: Infrastructure {target_id} is not registered in {details['location']}", 400
            if not mongoUtils.find(
                "nfvo_vim_links",
                {"nfvo_id": current["nfvo-id"], "vim_id": target_id},
            ):
                return f"Error: Infrastructure {target_id} is not linked to NFVO {current['nfvo-id']}", 400
        return None

    def index(self):
        """
        Returns a list of slices and their details,
        used by: `katana slice ls`
        """
        slice_data = mongoUtils.index("slice")
        return_data = []
        for islice in slice_data:
            return_data.append(dict(_id=islice["_id"], name=islice["slice_name"], created_at=islice["created_at"], status=islice["status"],))
        return dumps(return_data), 200

    @route("/observability")
    def observability_index(self):
        """
        Returns frontend-friendly monitoring/log links for all existing slices.
        """
        include_prometheus = request.args.get("include_prometheus") == "true"
        slice_data = mongoUtils.index("slice")
        return dumps(
            [
                self._slice_observability_payload(islice, include_prometheus=include_prometheus)
                for islice in slice_data
            ]
        ), 200

    def get(self, uuid):
        """
        Returns the details of specific slice,
        used by: `katana slice inspect [uuid]`
        """
        data = mongoUtils.get("slice", uuid)
        if data:
            return dumps(data), 200
        else:
            return "Not Found", 404

    @route("/<uuid>/observability")
    def show_observability(self, uuid):
        """
        Returns frontend-friendly monitoring/log links for one slice.
        """
        islice = mongoUtils.get("slice", uuid)
        if not islice:
            return "Slice not found", 404

        include_prometheus = request.args.get("include_prometheus", "true") != "false"
        return dumps(
            self._slice_observability_payload(islice, include_prometheus=include_prometheus)
        ), 200

    @route("/<uuid>/monitoring")
    def show_monitoring(self, uuid):
        """
        Returns monitoring details for one slice.
        """
        islice = mongoUtils.get("slice", uuid)
        if not islice:
            return "Slice not found", 404

        include_prometheus = request.args.get("include_prometheus", "true") != "false"
        payload = self._slice_observability_payload(
            islice,
            include_prometheus=include_prometheus,
        )
        return dumps(payload["monitoring"]), 200

    @route("/<uuid>/monitoring/summary")
    def show_monitoring_summary(self, uuid):
        """
        Returns frontend-ready current monitoring values for one slice.
        """
        islice = mongoUtils.get("slice", uuid)
        if not islice:
            return "Slice not found", 404

        return dumps(self._monitoring_summary_payload(islice)), 200

    @route("/<uuid>/monitoring/range")
    def show_monitoring_range(self, uuid):
        """
        Returns Prometheus range values for one known slice metric query.
        """
        islice = mongoUtils.get("slice", uuid)
        if not islice:
            return "Slice not found", 404

        metric = request.args.get("metric")
        queries = (
            self._slice_prometheus_queries(islice, include_infrastructure=True)
            if "slice_monitoring" in islice
            else {}
        )
        if not metric or metric not in queries:
            return dumps({"error": "Unknown metric", "available_metrics": sorted(queries.keys())}), 400

        start, end, step = self._range_window()
        result = self._query_prometheus_range(queries[metric], start, end, step)
        return dumps(
            {
                "_id": islice["_id"],
                "metric": metric,
                "query": queries[metric],
                "start": start,
                "end": end,
                "step": step,
                "result": result,
            }
        ), 200

    @route("/<uuid>/alerts")
    def show_alerts(self, uuid):
        """
        Returns stored Alertmanager events for one slice.
        """
        islice = mongoUtils.get("slice", uuid)
        if not islice:
            return "Slice not found", 404

        return dumps(
            {
                "_id": islice["_id"],
                "name": self._slice_name(islice),
                "alerts": self._slice_alerts(uuid, self._request_limit()),
            }
        ), 200

    @route("/<uuid>/logs")
    def show_logs(self, uuid):
        """
        Returns stored slice events, alerts, and best-effort matching NBI log lines.
        """
        islice = mongoUtils.get("slice", uuid)
        if not islice:
            return "Slice not found", 404

        limit = self._request_limit()
        alert_events = self._slice_alert_events(uuid, limit)
        payload = {
            "_id": islice["_id"],
            "name": self._slice_name(islice),
            "status": islice.get("status"),
            "events": self._slice_state_events(islice) + alert_events,
            "alerts": [event["alert"] for event in alert_events],
            "log_lines": self._local_slice_log_lines(uuid, limit),
            "log_count": None,
            "limit": limit,
            "note": (
                "events include stored slice state and alert records. log_lines are "
                "best-effort matches from this API container's rotating katana.log files."
            ),
        }
        payload["log_count"] = len(payload["log_lines"])
        return dumps(payload), 200

    @route("/<uuid>/time")
    def show_time(self, uuid):
        """
        Returns deployment time of a slice
        """
        islice = mongoUtils.get("slice", uuid)
        if islice:
            return dumps(islice["deployment_time"]), 200
        else:
            return "Not Found", 404

    @route("/<uuid>/modify", methods=["POST"])
    def modify(self, uuid):
        """
        Update the details of a specific slice.
        used by: `katana slice modify -f [file] [uuid]`
        """
        result = mongoUtils.get("slice", uuid)
        if not result:
            return f"Error: No such slice: {uuid}", 404
        validation_error = self._validate_modify_payload(result, request.json)
        if validation_error:
            return validation_error
        # Send the message to katana-mngr
        producer = kafkaUtils.create_producer()
        slice_message = {"action": "update", "slice_id": uuid, "updates": request.json}
        producer.send("slice", value=slice_message)
        return f"Updating {uuid}", 200

    def post(self):
        """
        Add a new slice. The request must provide the slice details.
        used by: `katana slice add -f [file]`
        """
        new_uuid = str(uuid.uuid4())
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return "Error: Request body must be a JSON object", 400
        if "infrastructure" in data:
            return "Error: infrastructure must be registered by Time-0 bootstrap", 400
        data["_id"] = new_uuid
        validation_error = self._validate_slice_payload(data)
        if validation_error:
            return validation_error
        mapping_validation_error = slice_mapping.validate_nest_request(data)
        if mapping_validation_error:
            return mapping_validation_error
        base_slice_descriptor = data["base_slice_descriptor"]
        if not base_slice_descriptor.get("base_slice_des_ref"):
            for field in slice_mapping.REQ_FIELDS:
                if field not in base_slice_descriptor:
                    return (
                        f"Error: Required field base_slice_descriptor.{field} is missing",
                        400,
                    )

        deployment_runtime, runtime_error = self._validate_deployment_targets(data)
        if runtime_error:
            return runtime_error

        # Get the NEST from the Slice Mapping process
        nest, error_code = slice_mapping.nest_mapping(data)

        if error_code:
            return nest, error_code

        if deployment_runtime:
            nest["deployment_runtime"] = deployment_runtime
        nest["target_selection_version"] = "katana/v1"

        # Store the asynchronous request before returning its UUID so immediate
        # frontend polling sees Queued instead of a transient 404.
        mongoUtils.add("slice", queued_slice_record(nest))
        try:
            producer = kafkaUtils.create_producer()
            slice_message = {"action": "add", "message": nest}
            producer.send("slice", value=slice_message)
        except Exception:
            mongoUtils.delete("slice", new_uuid)
            raise

        return new_uuid, 201

    def delete(self, uuid):
        """
        Delete a specific slice.
        used by: `katana slice rm [uuid]`
        """

        # Check if slice uuid exists
        delete_json = mongoUtils.get("slice", uuid)
        try:
            force = request.args["force"]
        except KeyError:
            force = None
        else:
            force = force if force == "true" else None

        if not delete_json:
            return f"Error: No such slice: {uuid}", 404
        else:
            # Send the message to katana-mngr
            producer = kafkaUtils.create_producer()
            slice_message = {"action": "delete", "message": uuid, "force": force}
            producer.send("slice", value=slice_message)
            return f"Deleting {uuid}", 200

    @route("<uuid>/errors")
    def show_errors(self, uuid):
        """
        Display the runitime errors of a slice
        """
        data = mongoUtils.get("slice", uuid)
        if data:
            runtime_errors = data.get("runtime_errors", {})
            return dumps(runtime_errors), 200
        else:
            return "Slice not found", 404
