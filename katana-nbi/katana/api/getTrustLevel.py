# -*- coding: utf-8 -*-
import logging
import time
import requests
from flask import request
from flask_classful import FlaskView
from bson.json_util import dumps

logger = logging.getLogger(__name__)

class getTrustLevelView(FlaskView):
    route_prefix = "/api/"
    route_base = "trustlevel"

    # Default targets
    DEFAULT_TARGETS = [
        {"serviceId": "81", "domainId": "8"},
        {"serviceId": "82", "domainId": "8"}
    ]

    # Cache Configuration
    JWT_TTL = 300       # Cache JWT for 5 minutes
    RESULT_TTL = 30     # Cache Trust Level results for 30 seconds
    
    # In-memory storage
    _jwt_cache = {}
    _result_cache = {}

    def get(self):
        """
        Triggers the TrustLevel check via GET.
        Uses background caching to prevent spamming the target APIs.
        """
        args = request.args
        target_url = args.get("target_url", "http://10.160.3.213:3001").rstrip("/")
        
        req_service_id = args.get("serviceId")
        req_domain_id = args.get("domainId")

        if req_service_id and req_domain_id:
            targets_to_check = [{"serviceId": req_service_id, "domainId": req_domain_id}]
        else:
            targets_to_check = self.DEFAULT_TARGETS

        logger.info(f"Starting TrustLevel check against: {target_url}")

        # 1. Fetch the JWT (Uses cache if available)
        try:
            token = self._get_jwt(target_url)
        except Exception as e:
            logger.error(f"TrustLevel JWT Authentication Failed: {e}")
            return dumps({"error": "Could not extract JWT", "details": str(e)}), 500

        # 2. Loop through targets and fetch trust levels
        results = []
        current_time = time.time()
        
        for target in targets_to_check:
            # Normalize numeric IDs exactly like the bash script
            service_id = str(target.get("serviceId", "81"))
            domain_id = str(target.get("domainId", "8"))
            
            if service_id.isdigit():
                service_id = f"service{service_id}"
            if domain_id.isdigit():
                domain_id = f"domain{domain_id}"

            # Check Result Cache first
            cache_key = f"{target_url}_{service_id}_{domain_id}"
            cached_data = self._result_cache.get(cache_key)
            
            if cached_data and (current_time - cached_data['timestamp']) < self.RESULT_TTL:
                logger.info(f"Serving cached TrustLevel for {service_id}")
                res = cached_data['data']
                res['cached'] = True  # Flag to let you know it came from the cache
                results.append(res)
            else:
                # Fetch fresh data and cache it
                res = self._get_trust_level(target_url, service_id, domain_id, token)
                res['cached'] = False
                self._result_cache[cache_key] = {
                    'data': res,
                    'timestamp': current_time
                }
                results.append(res)

        logger.info("TrustLevel sequence completed.")
        return dumps({
            "message": "Trust Level retrieval finished",
            "target": target_url,
            "results": results
        }), 200

    def _get_jwt(self, base_url):
        """Fetches the JWT using requests, with a 5-minute cache."""
        current_time = time.time()
        cached_token_data = self._jwt_cache.get(base_url)
        
        # Return cached token if it's still fresh
        if cached_token_data and (current_time - cached_token_data['timestamp']) < self.JWT_TTL:
            logger.debug(f"Using cached JWT for {base_url}")
            return cached_token_data['token']

        # Otherwise, fetch a new one
        url = f"{base_url}/issueJwtToken"
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        
        parsed = res.json()
        new_token = res.text.strip()
        
        if isinstance(parsed, dict):
            for k in ("data", "jwtEverything", "jwt", "token", "access_token"):
                v = parsed.get(k)
                if isinstance(v, str) and v.count(".") >= 2:
                    new_token = v.strip()
                    break
                    
        # Save to cache
        self._jwt_cache[base_url] = {
            'token': new_token,
            'timestamp': current_time
        }
        
        return new_token

    def _get_trust_level(self, base_url, service_id, domain_id, token):
        """Tries multiple auth headers and extracts the trust level."""
        url = f"{base_url}/api/transactions/getLastActualTrustLevel"
        params = {"serviceId": service_id, "domainId": domain_id}
        
        headers_to_try = [
            {"Authorization": f"Bearer {token}"},
            {"X-Access-Token": token},
            {"X-Api-Key": token},
            {"Authorization": f"JWT {token}"}
        ]
        
        result = {"serviceId": service_id, "domainId": domain_id}
        resp_json = None
        success = False

        logger.info(f"GET {url}?serviceId={service_id}&domainId={domain_id}")

        for headers in headers_to_try:
            try:
                res = requests.get(url, params=params, headers=headers, timeout=20)
                if res.status_code < 400:
                    try:
                        resp_json = res.json()
                    except ValueError:
                        resp_json = res.text
                        
                    result["status"] = "OK"
                    result["code"] = res.status_code
                    success = True
                    break
            except requests.exceptions.RequestException:
                continue
                
        if not success:
            result["status"] = "FAIL"
            result["error"] = "All auth header attempts failed or returned >= 400."
            return result

        result["raw_response"] = resp_json
        trust_level = self._extract_trust_level(resp_json)
        
        if trust_level is not None:
            result["trustLevel"] = str(trust_level)
        else:
            result["warning"] = "No trustLevel field found in response."
            
        return result

    def _extract_trust_level(self, data):
        """Recursively searches JSON for the trust level key."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key in ("trustLevel", "trust_level", "TrustLevel"):
                    return value
                if isinstance(value, (dict, list)):
                    res = self._extract_trust_level(value)
                    if res is not None:
                        return res
        elif isinstance(data, list):
            for item in data:
                res = self._extract_trust_level(item)
                if res is not None:
                    return res
        return None