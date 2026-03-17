# -*- coding: utf-8 -*-
"""
PAO (PPO-based Attack Observer) alert receiver.

Exposes two root-level endpoints consumed by pao_evaluate.py:
  POST /mitigate   {"AttackDetected": 1}
  POST /recovered  {"Recovered": 1}

Mitigation (mirrors orchestrator.py execute_mitigation):
  1. SSH into the UERANSIM VM and collect UE tunnel IPs (uesimtun0..19).
  2. Block every UE IP via the remote firewall API (iptables agent).
  3. SSH: kill nr-ue / nr-gnb, restart them.
"""

import logging
import threading
import time
from logging import handlers

import paramiko
import requests as http_client
from flask import request, jsonify
from flask_classful import FlaskView, route

from katana.shared_utils.mongoUtils import mongoUtils

# ── Logging ────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
file_handler = handlers.RotatingFileHandler("katana.log", maxBytes=10000, backupCount=5)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
logger.propagate = False

# ── UERANSIM VM ───────────────────────────────────────────────────────────────
UERANSIM_HOST = "10.160.201.88"
UERANSIM_USER = "localadmin"
UERANSIM_PASS = "ii70mseq"

# systemctl commands — sudo -S reads the password from stdin (no tty needed)
_SUDO_S = f"echo '{UERANSIM_PASS}' | sudo -S"
GNB_RESTART = f"{_SUDO_S} systemctl restart nr-gnb"
UE_RESTART  = f"{_SUDO_S} systemctl restart nr-ue"

# ── Firewall enforcement API ───────────────────────────────────────────────────
FIREWALL_API = "http://10.160.101.147:4445"

# ── MongoDB collection ─────────────────────────────────────────────────────────
_PAO_COLLECTION = "pao_events"

# Guard: only run one mitigation at a time
_mitigate_lock = threading.Lock()
_mitigating = False


# ── SSH helpers ────────────────────────────────────────────────────────────────

def _ssh_connect() -> paramiko.SSHClient:
    """Open an SSH connection to the UERANSIM VM."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        UERANSIM_HOST,
        username=UERANSIM_USER,
        password=UERANSIM_PASS,
        timeout=10,
    )
    return client


def _ssh_exec(client: paramiko.SSHClient, cmd: str, timeout: int = 30) -> str:
    """Run *cmd* on *client*, wait for it to finish, return combined output."""
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    stdout.channel.recv_exit_status()
    return stdout.read().decode(errors="ignore") + stderr.read().decode(errors="ignore")


def _get_ue_ips_via_ssh() -> list:
    """
    SSH into the UERANSIM VM and collect tunnel interface IPs (uesimtun0-19).
    Falls back to the hardcoded 10.45.0.2-21 range if SSH fails.
    """
    try:
        client = _ssh_connect()
        # ip -4 addr shows all IPv4 addresses; grep filters only uesimtun lines
        out = _ssh_exec(
            client,
            "ip -4 addr show | grep -A1 uesimtun | grep inet | awk '{print $2}' | cut -d/ -f1",
        )
        client.close()
        ips = [line.strip() for line in out.splitlines() if line.strip()]
        logger.info("UE IPs from SSH: %s", ips)
        return ips if ips else _fallback_ips()
    except Exception as exc:
        logger.error("SSH get_ue_ips failed: %s — using fallback range", exc)
        return _fallback_ips()


def _fallback_ips() -> list:
    """Hardcoded UE IP pool used when SSH enumeration is unavailable."""
    return [f"10.45.0.{i}" for i in range(2, 22)]


# ── Firewall helpers ───────────────────────────────────────────────────────────

def _call_firewall(endpoint: str, ips: list) -> dict:
    """POST to FIREWALL_API/<endpoint> for every IP. Returns per-IP results."""
    results = {}
    for ip in ips:
        url = f"{FIREWALL_API}/{endpoint}"
        try:
            r = http_client.post(url, json={"ip": ip}, timeout=5)
            results[ip] = r.json()
            if endpoint != "unblock":
                logger.info("Firewall %s %s -> %s", endpoint, ip, r.json())
        except Exception as exc:
            results[ip] = {"status": "error", "message": str(exc)}
            logger.error("Firewall %s %s failed: %s", endpoint, ip, exc)
    return results


# ── MongoDB helpers ────────────────────────────────────────────────────────────

def _store_event(event_type: str, payload: dict) -> dict:
    doc = {
        "event_type": event_type,
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "payload": payload,
    }
    mongoUtils.add(_PAO_COLLECTION, doc)
    return doc


# ── Background mitigation (non-blocking) ──────────────────────────────────────

def _execute_mitigation(blocked_ips: list):
    """
    Mirrors orchestrator.py execute_mitigation():
      1. Block UE IPs via firewall API.
      2. SSH: kill + restart nr-gnb and nr-ue.
    Runs in a daemon thread so the HTTP response returns immediately.
    """
    global _mitigating
    try:
        # 1. Block IPs
        logger.warning("Mitigation: blocking %d IPs via firewall...", len(blocked_ips))
        _call_firewall("block", blocked_ips)

        # 2. Restart RAN services on UERANSIM VM
        try:
            client = _ssh_connect()
            # Kill existing processes — sudo -S reads password from stdin (no tty needed)
            kill_cmd = (
                f"echo '{UERANSIM_PASS}' | sudo -S pkill -9 nr-ue 2>/dev/null; "
                f"echo '{UERANSIM_PASS}' | sudo -S pkill -9 nr-gnb 2>/dev/null; "
                "exit 0"
            )
            _ssh_exec(client, kill_cmd, timeout=15)
            # Stop attack script silently
            # Restart via systemctl — blocks until the service is confirmed running
            _ssh_exec(client, GNB_RESTART, timeout=20)
            time.sleep(3)
            _ssh_exec(client, UE_RESTART, timeout=20)
            client.close()
        except Exception as exc:
            logger.error("Mitigation: SSH restart failed: %s: %s", type(exc).__name__, exc)
    finally:
        _mitigating = False


class PaoAlertView(FlaskView):
    """
    Receives security alerts from the PAO (pao_evaluate.py) agent.

    Endpoints:
      POST /mitigate   {"AttackDetected": 1}
      POST /recovered  {"Recovered": 1}
    """

    route_prefix = "/"
    route_base = ""

    @route("mitigate", methods=["POST"])
    def mitigate(self):
        """
        Attack detected (action 0 → 1).
        1. SSH to UERANSIM VM to enumerate live UE IPs.
        2. Block them via firewall API + restart gNB/UE (background thread).
        """
        global _mitigating

        payload = request.get_json(force=True, silent=True) or {}
        logger.warning("PAO alert: ATTACK DETECTED | remote=%s", request.remote_addr)

        with _mitigate_lock:
            if _mitigating:
                return jsonify({"status": "already_mitigating"}), 202
            _mitigating = True

        # Collect UE IPs via SSH (fast — just reads interface list)
        ue_ips = _get_ue_ips_via_ssh()

        # Persist event with the IPs we are about to block
        payload["blocked_ips"] = ue_ips
        doc = _store_event("attack_detected", payload)

        # Run the slow parts (block + restart) in the background
        t = threading.Thread(target=_execute_mitigation, args=(ue_ips,), daemon=True)
        t.start()

        return jsonify({
            "status": "ok",
            "event": "attack_detected",
            "received_at": doc["timestamp_iso"],
            "blocking_ips": ue_ips,
        }), 200

    @route("recovered", methods=["POST"])
    def recovered(self):
        """
        System recovered (action 1 → 0).
        1. SSH: kill the attack script (ue_post_attack.py).
        2. Keep blocked IPs unchanged (unblock is disabled).
        """
        payload = request.get_json(force=True, silent=True) or {}
        logger.info("PAO alert: SYSTEM RECOVERED | remote=%s", request.remote_addr)


        doc = _store_event("system_recovered", payload)

        return jsonify({
            "status": "ok",
            "event": "system_recovered",
            "received_at": doc["timestamp_iso"],
        }), 200
