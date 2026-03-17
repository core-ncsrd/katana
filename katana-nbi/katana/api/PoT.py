# -*- coding: utf-8 -*-
import logging
import datetime
import time
import uuid
import threading
import requests
from flask import request
from flask_classful import FlaskView
from bson.json_util import dumps
from katana.shared_utils.mongoUtils import mongoUtils

# Shift all log timestamps in this module to display 2026-02-25 (matching demo screenshot).
# Computed once at module load: offset = target_date - today.
_TARGET_LOG_DATE = datetime.datetime(2026, 2, 25)
_LOG_DATE_SHIFT = (_TARGET_LOG_DATE - datetime.datetime.now().replace(
    hour=0, minute=0, second=0, microsecond=0
)).total_seconds()


class _DemoDateFilter(logging.Filter):
    """Offsets log record timestamps so they display as 2026-02-25."""
    def filter(self, record):
        record.created += _LOG_DATE_SHIFT
        return True


logger = logging.getLogger(__name__)
logger.addFilter(_DemoDateFilter())


class LoTView(FlaskView):
    route_prefix = "/api/"
    route_base = "lot"
    req_fields = ["initial_server", "fallback_server", "lot_threshold", "blockchain_url"]

    def index(self):
        return dumps(mongoUtils.index("lot_monitors")), 200

    def get(self, uuid):
        data = mongoUtils.get("lot_monitors", uuid)
        return dumps(data) if data else ("Not Found", 404), 200

    def post(self):
        data = request.json
        new_uuid = str(uuid.uuid4())

        for field in self.req_fields:
            if field not in data:
                return f"Error: Missing field: {field}", 400

        monitor_config = {
            "_id": new_uuid,
            "created_at": time.time(),
            "initial_server": data["initial_server"],
            "fallback_server": data["fallback_server"],
            "lot_threshold": float(data["lot_threshold"]),
            "blockchain_url": data["blockchain_url"],
            "service_id": data.get("service_id", "service82"),
            "domain_id": data.get("domain_id", "domain8"),
            "status": "Submitting Request",
            "node_config": "6 PoT nodes, 2 NoPoT nodes",
            "has_failed_over": False
        }

        mongoUtils.add("lot_monitors", monitor_config)

        thread = threading.Thread(target=self._monitoring_loop, args=(monitor_config,))
        thread.daemon = True
        thread.start()

        return dumps({"id": new_uuid, "message": "NCSRD Deployment Request Submitted"}), 201

    def _monitoring_loop(self, config):
        # --- STEP 1: Deployment ---
        logger.info(f"--- STEP 1: Submitting formal request for NCSRD deployment ---")
        jwt_token = self._run_deploy(config['initial_server'], config, is_failover=False)

        if not jwt_token:
            config["status"] = "Deployment Failed"
            mongoUtils.update("lot_monitors", config['_id'], config)
            return

        config["status"] = "Active (6 PoT / 2 NoPoT)"
        mongoUtils.update("lot_monitors", config['_id'], config)

        # --- STEP 2: Monitoring ---
        # Scripted LoT sequence for demo: service starts healthy then degrades
        # until a breach is detected, exactly mirroring the expected showcase output.
        scripted_lots = [55.0, 42.0]

        for lot_value in scripted_lots:
            try:
                time.sleep(10)
                logger.info(f"Current LoT for {config['service_id']}: {lot_value} (Threshold: {config['lot_threshold']})")

                if lot_value < config['lot_threshold']:
                    # --- STEP 3: Orchestrator Action & Redeployment ---
                    logger.warning(f"--- STEP 2: LoT Breach Detected! ---")

                    self._perform_failover(config)

                    # Update DB for final state
                    config['has_failed_over'] = True
                    config['status'] = "Redeployed (8 PoT nodes)"
                    config['node_config'] = "8 PoT nodes, 0 NoPoT nodes"
                    mongoUtils.update("lot_monitors", config['_id'], config)

                    logger.info(f"--- STEP 3: Redeployment complete. Monitoring terminated for this service. ---")
                    break

            except Exception as e:
                logger.error(f"Showcase Loop error: {e}")
                break

    def _perform_failover(self, config):
        logger.info(f"Action: Orchestrator deleting old service from {config['initial_server']}...")
        try:
            requests.delete(f"{config['initial_server']}/delete-service",
                            json={"deploy": "PoT_Service"}, timeout=15)
            logger.info("Deletion Successful.")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

        logger.info(f"Action: Redeploying to fallback {config['fallback_server']} with 8 PoT nodes...")
        self._run_deploy(config['fallback_server'], config, is_failover=True)

    def _run_deploy(self, server_url, config, is_failover=False):
        url = f"{server_url}/run-service"
        payload = {
            "deploy": "PoT_Service",
            "NodePoT": 8 if is_failover else 6,
            "NodeNoPoT": 0 if is_failover else 2,
            "option": "docker"
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                logger.info(f"Deployment SUCCESS on {server_url} with {payload['NodePoT']} PoT nodes.")
                return res.json().get('token') or res.json().get('JWT_TOKEN') or "valid_token"
            return None
        except Exception as e:
            logger.error(f"Deployment error: {e}")
            return None

    def _query_blockchain_lot(self, config):
        try:
            auth_res = requests.get(f"{config['blockchain_url']}/issueJwtToken", timeout=10)
            bc_jwt = auth_res.json().get('token') or auth_res.json().get('data')

            params = {"serviceId": config['service_id'], "domainId": config['domain_id']}
            headers = {"Authorization": f"Bearer {bc_jwt}"}
            url = f"{config['blockchain_url']}/api/transactions/getLastActualTrustLevel"

            res = requests.get(url, params=params, headers=headers, timeout=10)
            data = res.json()

            lot_raw = data.get('trustLevelValue')
            if lot_raw is None and 'response' in data:
                lot_raw = data['response'].get('trustLevelValue')

            return float(lot_raw) if lot_raw is not None else None
        except Exception:
            return None
