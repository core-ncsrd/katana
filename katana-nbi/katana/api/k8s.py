# -*- coding: utf-8 -*-
import logging
from marshal import dumps
import os
import time
import uuid
import werkzeug
import yaml
from flask import jsonify, request
from flask_classful import FlaskView
import pymongo
import requests  # type: ignore

from katana.shared_utils.mongoUtils import mongoUtils
from katana.shared_utils.nfvoUtils import osmUtils

# Logging Parameters
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class K8SClusterView(FlaskView):
    route_prefix = "/api/"
    route_base = "/k8s"
    req_fields = ["name", "vim_account", "k8s_version", "credentials"]
    

    def index(self):
        """
        Returns a list of Kubernetes clusters and their details.
        """
        logger.info("Fetching list of Kubernetes clusters")
        try:
            k8s_data = mongoUtils.index("k8sclusters")
            return_data = [
                {
                    "_id": str(cluster["_id"]),  # Convert ObjectId to string if needed
                    "name": cluster["name"],
                    "vim_account": cluster["vim_account"],
                    "created_at": cluster["created_at"],
                    "namespace": cluster.get("namespace", "default"),
                }
                for cluster in k8s_data
            ]
            logger.debug(f"Fetched clusters: {return_data}")
            return jsonify(return_data), 200  # Use Flask's jsonify for proper JSON response
        except Exception as e:
            logger.exception("Error fetching Kubernetes clusters")
            return f"Error: {str(e)}", 500


    def get(self, uuid):
        """
        Returns the details of a specific Kubernetes cluster.
        """
        logger.info(f"Fetching details for Kubernetes cluster: {uuid}")
        try:
            data = mongoUtils.get("k8sclusters", uuid)
            if data:
                logger.debug(f"Cluster details: {data}")
                return dumps(data), 200
            else:
                logger.warning(f"Cluster not found: {uuid}")
                return "Not Found", 404
        except Exception as e:
            logger.exception(f"Error fetching details for cluster {uuid}")
            return f"Error: {str(e)}", 500
        
        
        
    
    def post(self):
        """
        Add a new Kubernetes cluster and register it with OSM, or handle a YAML file upload.
        """
        if request.content_type.startswith("multipart/form-data"):
            # Handle file upload
            logger.info("Received a file upload request for Kubernetes credentials.")
            try:
                # Check if the request contains files
                if "file" not in request.files:
                    logger.warning("File not found in request payload.")
                    return jsonify({"error": "Missing file in request payload"}), 400

                creds_file = request.files["file"]

                # Sanitize filename to prevent directory traversal attacks
                creds_name = os.path.basename(creds_file.filename)
                if not creds_name:
                    logger.warning("Invalid file name received.")
                    return jsonify({"error": "Invalid file name"}), 400

                creds_dir = "creds"
                os.makedirs(creds_dir, exist_ok=True)  # Ensure directory exists
                creds_path = os.path.join(creds_dir, creds_name)

                # Save the uploaded file to the creds directory
                creds_file.save(creds_path)
                logger.info(f"Credentials file saved successfully: {creds_path}")

                return jsonify({"message": f"Credentials '{creds_name}' uploaded successfully."}), 201
            except Exception as e:
                logger.exception("Error uploading credentials.")
                return jsonify({"error": str(e)}), 500

        elif request.content_type == "application/json":
            # Handle JSON payload for adding a Kubernetes cluster
            new_uuid = str(uuid.uuid4())
            request.json["_id"] = new_uuid
            request.json["created_at"] = time.time()  # Unix epoch

            logger.info("Adding a new Kubernetes cluster.")
            logger.debug(f"Received payload: {request.json}")

            # Validate required fields
            for field in self.req_fields:
                if field not in request.json:
                    logger.error(f"Missing required field: {field}")
                    return jsonify({"error": f"Missing required field '{field}'"}), 400

            try:
                # Load the credentials file from the 'creds' directory
                creds_filename = request.json["credentials"]
                creds_path = os.path.join("creds", creds_filename)
                if not os.path.exists(creds_path):
                    logger.error(f"Credentials file not found: {creds_filename}")
                    return jsonify({"error": f"Credentials file not found: {creds_filename}"}), 400

                with open(creds_path, "r") as creds_file:
                    creds_data = yaml.safe_load(creds_file)
                    logger.debug(f"Parsed credentials: {creds_data}")

                # Prepare the OSM payload
                vim_account = request.json["vim_account"]
                payload = {
                    "name": request.json["name"],
                    "credentials": creds_data,  # Use parsed credentials
                    "vim_account": vim_account,
                    "k8s_version": request.json["k8s_version"],
                    "nets": request.json.get("nets", {}),
                    "namespace": request.json.get("namespace", "default"),
                    "deployment_methods": request.json.get("deployment_methods", {}),
                }

                # Create an OSM object
                osm = osmUtils.Osm(
                    nfvo_id=request.json.get("nfvo_id", ""),
                    ip=request.json.get("nfvo_ip", ""),
                    username=request.json.get("nfvo_username", ""),
                    password=request.json.get("nfvo_password", ""),
                    project_id=request.json.get("project_id", "admin"),
                )
                osm.getToken()

                # Send payload to OSM
                osm_url = f"https://{osm.ip}/osm/admin/v1/k8sclusters"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {osm.token}",
                }
                response = requests.post(osm_url, headers=headers, json=payload, verify=False)
                logger.debug(f"OSM API response: {response.status_code}, {response.text}")

                if response.status_code not in [200, 201,202]:
                    logger.error(f"Failed to add cluster to OSM: {response.text}")
                    return jsonify({"error": f"Failed to add Kubernetes cluster to OSM: {response.text}"}), response.status_code

                # Add the cluster to the database
                mongoUtils.add("k8sclusters", request.json)
                logger.info(f"Successfully added Kubernetes cluster: {new_uuid}")
                return jsonify({"message": "Kubernetes cluster added successfully", "id": new_uuid}), 201

            except pymongo.errors.DuplicateKeyError:
                logger.error(f"Cluster already exists: {request.json['name']}")
                return jsonify({"error": f"Kubernetes cluster with name {request.json['name']} already exists"}), 400
            except Exception as e:
                logger.exception("Error adding Kubernetes cluster.")
                return jsonify({"error": str(e)}), 500
        else:
            logger.warning("Unsupported content type.")
            return jsonify({"error": "Unsupported content type. Only JSON and file uploads are allowed."}), 415

        
    def delete(self, uuid):
        """
        Delete a specific Kubernetes cluster from OSM and the database.
        """
        logger.info(f"Deleting Kubernetes cluster: {uuid}")
        try:
            cluster = mongoUtils.get("k8sclusters", uuid)
            if not cluster:
                logger.warning(f"Cluster not found: {uuid}")
                return f"Error: No such Kubernetes cluster: {uuid}", 404

            # Fetch VIM account
            vim_account = mongoUtils.get("vim_accounts", cluster["vim_account"])
            if not vim_account:
                logger.error(f"VIM account not found: {cluster['vim_account']}")
                return f"Error: VIM account {cluster['vim_account']} not found", 404

            # Create an OSM object
            osm = osmUtils.Osm(
                nfvo_id=vim_account["nfvo_id"],
                ip=vim_account["nfvo_ip"],
                username=vim_account["nfvo_username"],
                password=vim_account["nfvo_password"],
                project_id=vim_account.get("project_id", "admin"),
            )
            osm.getToken()

            osm_url = f"https://{osm.ip}/osm/admin/v1/k8sclusters/{uuid}"
            headers = {"Authorization": f"Bearer {osm.token}"}
            response = requests.delete(osm_url, headers=headers, verify=False)
            logger.debug(f"OSM API response: {response.status_code}, {response.text}")

            if response.status_code not in [200, 204]:
                logger.error(f"Failed to delete cluster from OSM: {response.text}")
                return f"Failed to delete Kubernetes cluster from OSM: {response.text}", response.status_code

            mongoUtils.delete("k8sclusters", uuid)
            logger.info(f"Successfully deleted Kubernetes cluster: {uuid}")
            return f"Deleted Kubernetes cluster {uuid}", 200

        except Exception as e:
            logger.exception("Error deleting Kubernetes cluster")
            return f"Error: {str(e)}", 500
