# -*- coding: utf-8 -*-
import logging
import requests
from flask import request
from flask_classful import FlaskView
from bson.json_util import dumps

logger = logging.getLogger(__name__)

class InitSGCView(FlaskView):
    route_prefix = "/api/"
    route_base = "initsgc"

    # The default payloads to send if the trigger doesn't specify any
    DEFAULT_PAYLOADS = [
        {
            "domainId": "domain8",
            "serviceId": "service81",
            "containerIDList": ["container811", "container812"],
            "privacySLA": {"pID": "pid1", "privacyNT": "privacyNT1"},
            "networkGraph": "networkGraph",
            "privacyIndex": "1"
        },
        {
            "domainId": "domain8",
            "serviceId": "service82",
            "containerIDList": ["container821", "container822"],
            "privacySLA": {"pID": "pid1", "privacyNT": "privacyNT1"},
            "networkGraph": "networkGraph",
            "privacyIndex": "1"
        }
    ]

    def post(self):
        """
        Trigger the InitSGC execution.
        You can pass a custom 'target_url' or custom 'payloads' in the JSON body,
        otherwise, it uses the defaults.
        """
        data = request.json or {}
        
        # Fallback to the target IP you provided, ensuring we avoid out-of-scope IPs
        target_url = data.get("target_url", "http://10.160.3.213:3001").rstrip("/")
        payloads_to_send = data.get("payloads", self.DEFAULT_PAYLOADS)

        logger.info(f"Starting InitSGC orchestration targetting: {target_url}")

        # 1. Fetch the JWT
        try:
            token = self._get_jwt(target_url)
        except Exception as e:
            logger.error(f"InitSGC JWT Authentication Failed: {e}")
            return dumps({"error": "Failed to authenticate with target API", "details": str(e)}), 500

        # 2. Loop through payloads and deploy
        results = []
        for pl in payloads_to_send:
            res = self._send_init(target_url, pl, token)
            results.append(res)

        logger.info("InitSGC orchestration sequence completed.")
        return dumps({
            "message": "InitSGC execution finished",
            "target": target_url,
            "results": results
        }), 200

    def _get_jwt(self, base_url):
        """Fetches the JWT using the requests library."""
        url = f"{base_url}/issueJwtToken"
        logger.debug(f"Fetching JWT from {url}")
        
        res = requests.get(url, timeout=15)
        res.raise_for_status() # Throw an exception if the status is 4xx or 5xx
        
        parsed = res.json()
        if isinstance(parsed, dict):
            for k in ("data", "jwtEverything", "jwt", "token", "access_token"):
                v = parsed.get(k)
                if isinstance(v, str) and v.count(".") >= 2:
                    return v.strip()
                    
        return res.text.strip()

    def _send_init(self, base_url, payload, token):
        """Sends the payload and neatly formats the response."""
        url = f"{base_url}/api/transactions/initsgc"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        service_id = payload.get("serviceId", "unknown_service")
        result = {"serviceId": service_id}
        
        try:
            logger.info(f"Submitting InitSGC payload for service: {service_id}")
            res = requests.post(url, json=payload, headers=headers, timeout=20)
            
            # Try parsing the target's response as JSON for cleaner final output
            try:
                out_data = res.json()
            except ValueError:
                out_data = res.text

            # Handle Success vs. Error states gracefully
            if res.status_code in (200, 201):
                result["status"] = "OK"
                result["code"] = res.status_code
                result["initSGC_output"] = out_data
            else:
                if "already initialised" in res.text.lower():
                    result["status"] = "OK"
                    result["note"] = "Service already initialized."
                    result["initSGC_output"] = out_data
                else:
                    result["status"] = "FAIL"
                    result["code"] = res.status_code
                    result["initSGC_output"] = out_data
                    logger.warning(f"InitSGC failed for {service_id}: HTTP {res.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"InitSGC network request failed for {service_id}: {e}")
            result["status"] = "ERROR"
            result["initSGC_output"] = f"Connection error: {str(e)}"
            
        return result