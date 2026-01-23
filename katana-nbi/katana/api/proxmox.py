import logging
from logging import handlers
import json
import ipaddress
import time
import urllib3
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from flask import request
from flask_classful import FlaskView, route
from katana.shared_utils.mongoUtils import mongoUtils
from proxmoxer import ProxmoxAPI

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Thread lock for VM ID generation
vm_id_lock = threading.Lock()

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


class ProxmoxView(FlaskView):
    """
    Proxmox VM management API using proxmoxer
    """
    # Flask-Classful automatically adds the class name 'proxmox' to the route_prefix
    route_prefix = "/api"

    def __init__(self):
        """Initialize the ProxmoxView class."""
        self.proxmox_collection = "proxmox"

    def _get_proxmox_connection(self, cluster):
        """
        Get a ProxmoxAPI connection object with thread safety
        """
        try:
            # Extract host and port from URL
            url = cluster["url"]
            if "://" in url:
                url = url.split("://")[1]  # Remove protocol
            if ":" in url:
                host, port = url.split(":")
            else:
                host = url
                port = 8006
            
            # Create ProxmoxAPI connection with longer timeout and thread safety
            proxmox = ProxmoxAPI(
                host, 
                user=cluster["username"], 
                password=cluster["password"],
                port=int(port),
                verify_ssl=False,
                timeout=30  # 30 second timeout
            )
            
            return {"success": True, "connection": proxmox}
        except Exception as e:
            logger.error(f"Failed to connect to Proxmox: {str(e)}")
            return {"success": False, "message": str(e)}

    def _test_connection(self, url, username, password, node):
        """
        Test connection to a Proxmox cluster using proxmoxer
        """
        try:
            # Extract host and port from URL
            if "://" in url:
                url = url.split("://")[1]  # Remove protocol
            if ":" in url:
                host, port = url.split(":")
            else:
                host = url
                port = 8006
            
            # Create ProxmoxAPI connection with longer timeout
            proxmox = ProxmoxAPI(
                host, 
                user=username, 
                password=password,
                port=int(port),
                verify_ssl=False,
                timeout=30  # 30 second timeout
            )
            
            # Test connection by getting node status
            node_status = proxmox.nodes(node).status.get()
            
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {"success": False, "message": str(e)}

    def _check_cluster_connectivity(self, cluster):
        """
        Check if a cluster is reachable using proxmoxer
        """
        connection_result = self._get_proxmox_connection(cluster)
        return "online" if connection_result["success"] else "offline"

    @route("/cluster", methods=["GET"])
    def get_clusters(self):
        """
        Get all registered Proxmox clusters
        """
        try:
            clusters = mongoUtils.index(self.proxmox_collection)
            return_data = []

            for cluster in clusters:
                # Don't return sensitive information
                cluster_info = {
                    "_id": cluster["_id"],
                    "name": cluster["name"],
                    "url": cluster["url"],
                    "username": cluster["username"],
                    "node": cluster["node"],
                    "status": self._check_cluster_connectivity(cluster)
                }
                return_data.append(cluster_info)
            
            return json.dumps(return_data), 200
        except Exception as e:
            logger.error(f"Error retrieving Proxmox clusters: {str(e)}")
            return {"error": str(e)}, 500

    @route("/cluster/<cluster_id>", methods=["GET"])
    def get_cluster(self, cluster_id):
        """
        Get details of a specific Proxmox cluster
        """
        try:
            cluster = mongoUtils.get(self.proxmox_collection, cluster_id)
            if not cluster:
                return {"error": f"Proxmox cluster with ID {cluster_id} not found"}, 404
            
            # Don't return sensitive information
            cluster_info = {
                "_id": cluster["_id"],
                "name": cluster["name"],
                "url": cluster["url"],
                "username": cluster["username"],
                "node": cluster["node"],
                "status": self._check_cluster_connectivity(cluster)
            }
            
            return json.dumps(cluster_info), 200
        except Exception as e:
            logger.error(f"Error retrieving Proxmox cluster {cluster_id}: {str(e)}")
            return {"error": str(e)}, 500

    @route("/cluster", methods=["POST"])
    def register_cluster(self):
        """
        Register a new Proxmox cluster
        """
        try:
            data = request.json
            
            # Validate required fields
            required_fields = ["name", "url", "username", "password", "node"]
            for field in required_fields:
                if field not in data:
                    return {"error": f"Missing required field: {field}"}, 400
            
            # Check if cluster with same name already exists
            existing_clusters = mongoUtils.index(self.proxmox_collection)
            for cluster in existing_clusters:
                if cluster["name"] == data["name"]:
                    return {"error": f"Cluster with name '{data['name']}' already exists"}, 409
            
            # Test connection to the cluster
            connection_test = self._test_connection(
                data["url"], 
                data["username"], 
                data["password"],
                data["node"]
            )
            
            if not connection_test["success"]:
                return {"error": f"Failed to connect to Proxmox cluster: {connection_test['message']}"}, 400
            
            # Generate a unique ID for the cluster
            import uuid
            cluster_id = str(uuid.uuid4())
            
            # Store the cluster information
            cluster_data = {
                "_id": cluster_id,
                "name": data["name"],
                "url": data["url"],
                "username": data["username"],
                "password": data["password"],
                "node": data["node"],
                "created_at": time.time()
            }
            
            mongoUtils.add(self.proxmox_collection, cluster_data)
            
            return {"message": "Proxmox cluster registered successfully", "cluster_id": cluster_id}, 201
        except Exception as e:
            logger.error(f"Error registering Proxmox cluster: {str(e)}")
            return {"error": str(e)}, 500

    @route("/cluster/<cluster_id>", methods=["DELETE"])
    def delete_cluster(self, cluster_id):
        """
        Delete a registered Proxmox cluster
        """
        try:
            cluster = mongoUtils.get(self.proxmox_collection, cluster_id)
            if not cluster:
                return {"error": f"Proxmox cluster with ID {cluster_id} not found"}, 404
            
            mongoUtils.delete(self.proxmox_collection, cluster_id)
            
            return {"message": f"Proxmox cluster {cluster_id} deleted successfully"}, 200
        except Exception as e:
            logger.error(f"Error deleting Proxmox cluster {cluster_id}: {str(e)}")
            return {"error": str(e)}, 500

    @route("/vm", methods=["POST"])
    def create_vm(self):
        """
        Create and configure Proxmox VMs as specified in the YAML configuration
        """
        try:
            # Get the VM configuration from the request
            config_data = request.json
            
            logger.info(f"Received Proxmox VM configuration: {config_data}")
            
            # Validate the configuration
            logger.info("Validating configuration...")
            validation_result = self._validate_config(config_data)
            if not validation_result["valid"]:
                logger.error(f"Configuration validation failed: {validation_result['message']}")
                return {"error": validation_result["message"]}, 400
            
            logger.info("Configuration validation passed")
            
            # Get the cluster to use
            logger.info("Looking up cluster...")
            cluster_id = config_data.get("cluster_id")
            if not cluster_id:
                # Use the cluster name if ID is not provided
                cluster_name = config_data.get("cluster_name")
                if not cluster_name:
                    logger.error("Neither cluster_id nor cluster_name provided")
                    return {"error": "Either cluster_id or cluster_name must be provided"}, 400
                
                logger.info(f"Looking up cluster by name: {cluster_name}")
                # Find the cluster by name
                clusters = mongoUtils.index(self.proxmox_collection)
                cluster = None
                for c in clusters:
                    if c["name"] == cluster_name:
                        cluster = c
                        break
                
                if not cluster:
                    logger.error(f"Cluster not found by name: {cluster_name}")
                    return {"error": f"Proxmox cluster with name '{cluster_name}' not found"}, 404
            else:
                logger.info(f"Looking up cluster by ID: {cluster_id}")
                # Find the cluster by ID
                cluster = mongoUtils.get(self.proxmox_collection, cluster_id)
                if not cluster:
                    logger.error(f"Cluster not found by ID: {cluster_id}")
                    return {"error": f"Proxmox cluster with ID '{cluster_id}' not found"}, 404
            
            logger.info(f"Found cluster: {cluster['name']}")
            
            # Check cluster connectivity
            logger.info("Checking cluster connectivity...")
            connectivity_status = self._check_cluster_connectivity(cluster)
            if connectivity_status != "online":
                logger.error(f"Cluster {cluster['name']} is not reachable: {connectivity_status}")
                return {"error": f"Proxmox cluster '{cluster['name']}' is not reachable"}, 503
            
            logger.info("Cluster connectivity check passed")
            
            # Pre-allocate unique VM IDs to avoid conflicts in parallel processing
            logger.info(f"Pre-allocating VM IDs for {len(config_data.get('vms', []))} VMs...")
            
            # Get Proxmox connection for ID allocation
            conn_result = self._get_proxmox_connection(cluster)
            if not conn_result["success"]:
                logger.error(f"Failed to connect to Proxmox for ID allocation: {conn_result['message']}")
                return {"error": f"Failed to connect to Proxmox: {conn_result['message']}"}, 503
            
            proxmox = conn_result["connection"]
            node = cluster["node"]
            
            # Pre-allocate all VM IDs sequentially to avoid conflicts
            allocated_vm_ids = []
            for i, vm_config in enumerate(config_data.get("vms", [])):
                max_attempts = 10
                vm_id = None
                
                for attempt in range(max_attempts):
                    try:
                        if attempt == 0:
                            # First try: get next available ID from Proxmox
                            candidate_id = proxmox.cluster.nextid.get()
                        else:
                            # Use incremental random ranges to avoid conflicts
                            candidate_id = random.randint(2000 + i * 100, 2000 + (i + 1) * 100 - 1)
                        
                        # Check if this ID is free and not already allocated
                        if candidate_id in allocated_vm_ids:
                            logger.warning(f"VM ID {candidate_id} already allocated to another VM")
                            continue
                        
                        # Check if VM exists in Proxmox
                        try:
                            existing_vm = proxmox.nodes(node).qemu(candidate_id).config.get()
                            logger.warning(f"VM ID {candidate_id} already exists in Proxmox")
                            continue
                        except:
                            # Good! VM ID is free
                            vm_id = candidate_id
                            allocated_vm_ids.append(vm_id)
                            logger.info(f"Allocated VM ID {vm_id} for {vm_config.get('name', 'unnamed')}")
                            break
                    except Exception as e:
                        logger.warning(f"Attempt {attempt + 1} failed for VM ID allocation: {e}")
                        continue
                
                if vm_id is None:
                    # Fallback to high random number
                    vm_id = random.randint(8000 + i * 10, 8000 + (i + 1) * 10 - 1)
                    allocated_vm_ids.append(vm_id)
                    logger.warning(f"Using fallback VM ID {vm_id} for {vm_config.get('name', 'unnamed')}")
            
            logger.info(f"Pre-allocated VM IDs: {allocated_vm_ids}")
            
            # Process VMs in parallel with pre-allocated IDs
            logger.info(f"Processing {len(config_data.get('vms', []))} VMs in parallel...")
            results = []
            
            def create_single_vm(vm_config, vm_index, assigned_vm_id):
                """Create a single VM with pre-assigned ID"""
                logger.info(f"Creating VM {vm_index+1}: {vm_config.get('name', 'unnamed')} with ID {assigned_vm_id}")
                return self._create_and_configure_vm(vm_config, cluster, assigned_vm_id)
            
            # Return immediate success response - VMs will be created in background
            logger.info(f"VM creation initiated for {len(config_data.get('vms', []))} VMs")
            
            # Create summary of what will be deployed
            deployment_summary = []
            for i, vm_config in enumerate(config_data.get("vms", [])):
                vm_summary = {
                    "vm_name": vm_config["name"],
                    "vm_id": allocated_vm_ids[i],
                    "template": vm_config["template"],
                    "cpu": vm_config["cpu"],
                    "ram": vm_config["ram"],
                    "disk_size": vm_config["disk_size"],
                    "status": "deployment_initiated",
                    "cluster": cluster["name"],
                    "networks": [
                        {
                            "name": bridge["name"],
                            "type": bridge["type"],
                            "ip": bridge.get("ip", "dhcp"),
                            "gateway": bridge.get("gateway", "auto")
                        }
                        for bridge in vm_config["bridges"]
                    ]
                }
                deployment_summary.append(vm_summary)
            
            # Start VM creation in background (fire and forget)
            def background_vm_creation():
                """Background VM creation process"""
                try:
                    results = []
                    def create_single_vm(vm_config, vm_index, assigned_vm_id):
                        logger.info(f"Background: Creating VM {vm_index+1}: {vm_config.get('name', 'unnamed')} with ID {assigned_vm_id}")
                        return self._create_and_configure_vm(vm_config, cluster, assigned_vm_id)
                    
                    with ThreadPoolExecutor(max_workers=min(4, len(config_data.get("vms", [])))) as executor:
                        futures = []
                        for i, vm_config in enumerate(config_data.get("vms", [])):
                            future = executor.submit(create_single_vm, vm_config, i, allocated_vm_ids[i])
                            futures.append(future)
                        
                        for future in as_completed(futures, timeout=120):
                            try:
                                result = future.result()
                                results.append(result)
                                logger.info(f"Background: VM {result.get('vm_name')} completed with status: {result.get('status')}")
                            except Exception as e:
                                logger.error(f"Background: VM creation failed: {e}")
                    
                    logger.info("Background: All VMs processed successfully")
                except Exception as e:
                    logger.error(f"Background VM creation error: {e}")
            
            # Start background thread
            from threading import Thread
            background_thread = Thread(target=background_vm_creation)
            background_thread.daemon = True
            background_thread.start()
            
            return {
                "message": "Proxmox VM deployment initiated successfully", 
                "deployment_status": "in_progress",
                "estimated_time": "2-3 minutes",
                "vms": deployment_summary
            }, 202  # HTTP 202 Accepted - processing in background
        
        except Exception as e:
            logger.error(f"Error creating Proxmox VMs: {str(e)}")
            return {"error": str(e)}, 500

    def _validate_config(self, config):
        """
        Validate the Proxmox VM configuration
        """
        # Check if either cluster_id or cluster_name is provided
        if "cluster_id" not in config and "cluster_name" not in config:
            return {"valid": False, "message": "Either cluster_id or cluster_name must be provided"}
        
        # Check if the configuration has a vms key
        if "vms" not in config or not isinstance(config["vms"], list):
            return {"valid": False, "message": "Configuration missing 'vms' list"}
        
        # Check each VM configuration
        for vm in config["vms"]:
            # Required fields
            required_fields = ["name", "template", "cpu", "ram", "storage_type", "disk_size", "bridges"]
            for field in required_fields:
                if field not in vm:
                    return {"valid": False, "message": f"VM configuration missing required field: {field}"}
            
            # Check bridges configuration
            if not isinstance(vm["bridges"], list):
                return {"valid": False, "message": "Bridges should be a list"}
            
            for bridge in vm["bridges"]:
                if "name" not in bridge or "type" not in bridge:
                    return {"valid": False, "message": "Bridge missing name or type"}
                
                # Check if custom IP is properly configured
                if bridge["type"] != "management":
                    required_net_fields = ["ip", "netmask", "gateway"]
                    for field in required_net_fields:
                        if field not in bridge:
                            return {"valid": False, "message": f"Custom bridge missing required field: {field}"}
                    
                    # Validate IP format
                    try:
                        ipaddress.ip_address(bridge["ip"])
                        ipaddress.ip_address(bridge["gateway"])
                    except ValueError:
                        return {"valid": False, "message": "Invalid IP address format"}
        
        return {"valid": True, "message": "Configuration is valid"}

    def _create_and_configure_vm(self, vm_config, cluster, pre_assigned_vm_id=None):
        """
        Create and configure a Proxmox VM based on the provided configuration using proxmoxer
        """
        vm_name = vm_config["name"]
        template = vm_config["template"]
        cpu = vm_config["cpu"]
        ram = vm_config["ram"]
        storage_type = vm_config["storage_type"]
        disk_size = vm_config["disk_size"]
        bridges = vm_config["bridges"]
        
        logger.info(f"Creating VM: {vm_name} from template {template}")
        
        try:
            # Get Proxmox connection
            conn_result = self._get_proxmox_connection(cluster)
            if not conn_result["success"]:
                raise Exception(f"Failed to connect to Proxmox: {conn_result['message']}")
            
            proxmox = conn_result["connection"]
            node = cluster["node"]
            
            # Step 1: Use pre-assigned VM ID (no more race conditions!)
            if pre_assigned_vm_id:
                next_vmid = pre_assigned_vm_id
                logger.info(f"Using pre-assigned VM ID: {next_vmid}")
            else:
                # Fallback to old method if no pre-assigned ID (backward compatibility)
                logger.warning("No pre-assigned VM ID provided, using fallback method")
                with vm_id_lock:
                    try:
                        next_vmid = proxmox.cluster.nextid.get()
                        logger.info(f"Using fallback VM ID: {next_vmid}")
                    except Exception as e:
                        next_vmid = random.randint(9000, 9999)
                        logger.warning(f"Fallback failed, using random ID: {next_vmid}")
            
            # Step 2: Clone the template to create a new VM
            logger.info(f"Cloning template {template} to VM {next_vmid} ({vm_name})")
            
            clone_data = {
                "newid": next_vmid,
                "name": vm_name,
                "full": 1,  # Full clone
                "storage": "fast",  # Target storage: fast
                "pool": "core_srvrs"  # Resource pool: core_srvs
            }
            
            # Override target storage if specified in config
            if storage_type:
                clone_data["storage"] = storage_type
            
            # Clone the template
            clone_task = proxmox.nodes(node).qemu(template).clone.post(**clone_data)
            logger.info(f"Clone task initiated: {clone_task}")
            
            # Wait for clone to complete by checking task status
            logger.info("Waiting for clone to complete...")
            task_id = clone_task
            max_wait = 120  # Maximum 2 minutes wait
            wait_time = 0
            
            while wait_time < max_wait:
                try:
                    # Check if task is complete by trying to get VM config
                    vm_config = proxmox.nodes(node).qemu(next_vmid).config.get()
                    logger.info("Clone completed successfully")
                    break
                except:
                    # VM not ready yet, wait more
                    time.sleep(5)
                    wait_time += 5
                    logger.info(f"Still waiting for clone... ({wait_time}s)")
            
            if wait_time >= max_wait:
                raise Exception("Clone operation timed out")
            
            # Brief wait for VM to be ready for configuration
            logger.info("Waiting for VM to be ready for configuration...")
            time.sleep(5)  # Reduced from 15 to 5 seconds
            
            # Step 3: Set CPU and RAM with retry logic
            logger.info(f"Setting VM resources: {cpu} cores, {ram} MB RAM")
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    config_data = {
                        "cores": cpu,
                        "memory": ram
                    }
                    proxmox.nodes(node).qemu(next_vmid).config.put(**config_data)
                    logger.info("VM resources configured successfully")
                    break
                except Exception as e:
                    retry_count += 1
                    if "lock" in str(e).lower() and retry_count < max_retries:
                        logger.warning(f"VM locked, waiting before retry {retry_count}/{max_retries}...")
                        time.sleep(5)  # Reduced from 10 to 5 seconds
                    else:
                        logger.error(f"Failed to set VM resources after {retry_count} attempts: {e}")
                        break
            
            # Step 4: Resize disk with retry logic  
            logger.info(f"Resizing disk to {disk_size}GB")
            retry_count = 0
            while retry_count < max_retries:
                try:
                    resize_data = {
                        "disk": "scsi0",
                        "size": f"{disk_size}G"
                    }
                    proxmox.nodes(node).qemu(next_vmid).resize.put(**resize_data)
                    logger.info("Disk resized successfully")
                    break
                except Exception as e:
                    retry_count += 1
                    if "lock" in str(e).lower() and retry_count < max_retries:
                        logger.warning(f"VM locked for disk resize, waiting before retry {retry_count}/{max_retries}...")
                        time.sleep(5)  # Reduced from 10 to 5 seconds
                    else:
                        logger.warning(f"Failed to resize disk after {retry_count} attempts: {e}")
                        break
            
            # Step 5: Configure network bridges
            net_index = 0
            bridge_results = []
            
            for bridge in bridges:
                bridge_name = bridge["name"]
                bridge_type = bridge["type"]
                
                logger.info(f"Adding network interface {net_index}: {bridge_name}")
                
                # Parse VLAN tag from bridge name (e.g., vmbr1.1601 -> bridge=vmbr1, tag=1601)
                if '.' in bridge_name:
                    bridge_base, vlan_tag = bridge_name.split('.', 1)
                    net_config = f"virtio,bridge={bridge_base},tag={vlan_tag}"
                    logger.info(f"Using bridge {bridge_base} with VLAN tag {vlan_tag}")
                else:
                    net_config = f"virtio,bridge={bridge_name}"
                    logger.info(f"Using bridge {bridge_name} without VLAN tag")
                
                config_update = {f"net{net_index}": net_config}
                
                try:
                    proxmox.nodes(node).qemu(next_vmid).config.put(**config_update)
                    logger.info(f"Network interface {net_index} added successfully")
                    
                    bridge_result = {
                        "name": bridge_name,
                        "type": bridge_type,
                        "index": net_index
                    }
                    
                    # Store custom network info for later configuration
                    if bridge_type != "management":
                        bridge_result["ip"] = bridge["ip"]
                        bridge_result["netmask"] = bridge["netmask"]
                        bridge_result["gateway"] = bridge["gateway"]
                    
                    bridge_results.append(bridge_result)
                    net_index += 1
                    
                except Exception as e:
                    logger.error(f"Failed to add network interface {net_index}: {e}")
            
            # Step 6: Configure cloud-init for automatic network setup
            logger.info("Configuring cloud-init for network setup...")
            try:
                self._configure_cloud_init_network(proxmox, node, next_vmid, bridge_results)
                logger.info("Cloud-init network configuration applied")
            except Exception as e:
                logger.warning(f"Cloud-init configuration failed: {e}")
            
            # Step 7: Start the VM
            logger.info("Starting VM...")
            try:
                proxmox.nodes(node).qemu(next_vmid).status.start.post()
                logger.info("VM start command sent successfully")
                
                # Wait for VM to boot up
                logger.info("Waiting for VM to boot...")
                time.sleep(30)  # Give VM time to boot
                
                # Step 8: Configure policy-based routing via SSH
                logger.info("Configuring policy-based routing via SSH...")
                ssh_result = self._configure_vm_via_ssh(bridge_results, next_vmid, vm_name)
                if ssh_result["success"]:
                    logger.info("SSH network configuration completed successfully")
                else:
                    logger.warning(f"SSH network configuration failed: {ssh_result['error']}")
                
            except Exception as e:
                logger.warning(f"Failed to start VM or configure network (VM created but may need manual setup): {e}")
            
            return {
                "vm_name": vm_name,
                "vm_id": next_vmid,
                "status": "created",
                "cluster": cluster["name"],
                "bridges": bridge_results,
                "network_method": "ssh-configured",
                "ssh_config_result": ssh_result if 'ssh_result' in locals() else {"success": False, "error": "Not attempted"}
            }
        
        except Exception as e:
            logger.error(f"Error creating VM {vm_name}: {str(e)}")
            return {
                "vm_name": vm_name,
                "status": "error",
                "error": str(e)
            }

    def _configure_cloud_init_network(self, proxmox, node, vm_id, bridge_results):
        """
        Configure basic network interfaces using cloud-init (SSH will handle advanced routing)
        """
        try:
            # Build basic cloud-init network configuration
            cloud_init_config = {}
            
            # Configure interfaces with basic settings
            management_configured = False
            
            for bridge in bridge_results:
                interface_index = bridge["index"]
                
                if bridge["type"] == "management" and not management_configured:
                    # Management interface - DHCP
                    cloud_init_config["ipconfig0"] = "ip=dhcp"
                    management_configured = True
                    logger.info(f"Configured management interface ipconfig0 via DHCP")
                    
                elif bridge["type"] != "management":
                    # Custom interface with static IP (no gateway - will be configured via SSH)
                    ip_address = bridge["ip"]
                    netmask = bridge["netmask"]
                    
                    # Convert netmask to CIDR
                    import ipaddress
                    cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
                    
                    # Configure interface (basic IP only, no gateway)
                    config_key = f"ipconfig{interface_index}"
                    config_value = f"ip={ip_address}/{cidr}"
                    cloud_init_config[config_key] = config_value
                    
                    logger.info(f"Configured {config_key}={config_value} (SSH will add routing)")
            
            # Set additional cloud-init parameters
            cloud_init_config.update({
                "ciuser": "ubuntu",
                "cipassword": "ubuntu",
                "sshkeys": "",
                "nameserver": "8.8.8.8 8.8.4.4",
                "searchdomain": "local"
            })
            
            # Apply cloud-init configuration to VM
            proxmox.nodes(node).qemu(vm_id).config.put(**cloud_init_config)
            
            logger.info(f"Applied basic cloud-init configuration: {cloud_init_config}")
            
            return {
                "success": True, 
                "config": cloud_init_config,
                "message": "Basic IP configuration applied. SSH will handle policy routing."
            }
            
        except Exception as e:
            logger.error(f"Failed to configure cloud-init: {e}")
            return {"success": False, "error": str(e)}

    def _generate_netplan_script(self, custom_networks):
        """
        Generate script to configure netplan with policy-based routing
        """
        if not custom_networks:
            return "# No custom networks to configure"
            
        script = """#!/bin/bash
# Configure netplan with policy-based routing
echo "Backing up current netplan..."
cp /etc/netplan/50-cloud-init.yaml /etc/netplan/50-cloud-init.yaml.backup

echo "Creating new netplan configuration..."
cat > /etc/netplan/50-cloud-init.yaml << 'EOF'
network:
  version: 2
  routing-policy:"""

        # Add routing policies
        for net in custom_networks:
            table_id = 100 + int(net['interface'][-1])  # eth1 -> table 101, eth2 -> table 102
            script += f"""
    - from: {net['ip']}/32
      table: {table_id}"""

        script += """
  ethernets:
    eth0:
      dhcp4: true
      set-name: "eth0\""""

        # Add custom interfaces
        for net in custom_networks:
            interface = net['interface']
            table_id = 100 + int(interface[-1])
            
            script += f"""
    {interface}:
      addresses:
        - {net['ip']}/{net['cidr']}
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
        search: [local]
      routes:
        - to: 0.0.0.0/0
          via: {net['gateway']}
          table: {table_id}
      set-name: "{interface}\""""

        script += """
'EOF'

echo "Applying netplan configuration..."
netplan apply

echo "Setting up routing rules (backup method)..."
"""

        # Add routing commands
        for net in custom_networks:
            table_id = 100 + int(net['interface'][-1])
            script += f"""ip rule add from {net['ip']}/32 table {table_id} 2>/dev/null || echo "Rule already exists for {net['ip']}"
ip route add default via {net['gateway']} table {table_id} 2>/dev/null || echo "Route already exists in table {table_id}"
"""

        script += """
echo "Configuration complete!"
echo "Testing connectivity..."
echo "Management interface: $(ip route show default | head -1)"
ip rule show
echo ""
echo "You can now SSH via management interface and use custom networks for applications."
"""

        return script

    def _generate_immediate_network_config(self, bridge_config, vm_running, vm_id):
        """
        Generate network configuration immediately without waiting for guest agent
        """
        try:
            bridge_name = bridge_config["name"]
            ip_address = bridge_config["ip"]
            gateway = bridge_config["gateway"]
            interface_index = bridge_config["index"]
            
            # Generate script immediately
            script_content = self._generate_network_config_script(bridge_config, interface_index)
            
            return {
                "bridge": bridge_name,
                "method": "script-ready",
                "status": "configured",
                "ip": ip_address,
                "gateway": gateway,
                "vm_id": vm_id,
                "interface": f"eth{interface_index}",
                "script": script_content,
                "instructions": f"VM {vm_id} is ready. Execute the script inside the VM to configure eth{interface_index} with IP {ip_address}"
            }
            
        except Exception as e:
            logger.error(f"Failed to generate network config: {e}")
            return {
                "bridge": bridge_config.get("name", "unknown"),
                "method": "failed", 
                "status": "error",
                "error": str(e)
            }

    def _configure_vm_network_interface(self, proxmox, node, vm_id, bridge_config, vm_running):
        """
        Configure a custom network interface inside the VM using cloud-init or QEMU guest agent
        """
        try:
            bridge_name = bridge_config["name"]
            ip_address = bridge_config["ip"]
            netmask = bridge_config["netmask"]
            gateway = bridge_config["gateway"]
            interface_index = bridge_config["index"]
            
            logger.info(f"Configuring network interface eth{interface_index} with IP {ip_address}")
            
            # Method 1: Try using cloud-init if VM supports it
            try:
                # Create network configuration for cloud-init
                network_config = self._create_cloud_init_network_config(bridge_config, interface_index)
                
                # Apply cloud-init configuration
                cloud_init_result = self._apply_cloud_init_config(proxmox, node, vm_id, network_config)
                if cloud_init_result["success"]:
                    return {
                        "bridge": bridge_name,
                        "method": "cloud-init",
                        "status": "configured",
                        "ip": ip_address,
                        "gateway": gateway
                    }
            except Exception as e:
                logger.debug(f"Cloud-init configuration failed: {e}")
            
            # Method 2: Try using QEMU guest agent if running
            if vm_running:
                try:
                    guest_agent_result = self._configure_via_guest_agent(
                        proxmox, node, vm_id, bridge_config, interface_index
                    )
                    if guest_agent_result["success"]:
                        return {
                            "bridge": bridge_name,
                            "method": "guest-agent",
                            "status": "configured",
                            "ip": ip_address,
                            "gateway": gateway
                        }
                except Exception as e:
                    logger.debug(f"Guest agent configuration failed: {e}")
            
            # Method 3: Prepare script for manual execution
            script_content = self._generate_network_config_script(bridge_config, interface_index)
            
            return {
                "bridge": bridge_name,
                "method": "manual-script",
                "status": "script-ready",
                "ip": ip_address,
                "gateway": gateway,
                "script": script_content,
                "instructions": f"Run the provided script inside VM {vm_id} to configure eth{interface_index}"
            }
            
        except Exception as e:
            logger.error(f"Failed to configure network interface: {e}")
            return {
                "bridge": bridge_config.get("name", "unknown"),
                "method": "failed",
                "status": "error",
                "error": str(e)
            }

    def _create_cloud_init_network_config(self, bridge_config, interface_index):
        """
        Create cloud-init network configuration
        """
        ip_address = bridge_config["ip"]
        netmask = bridge_config["netmask"]
        gateway = bridge_config["gateway"]
        
        # Convert netmask to CIDR notation
        import ipaddress
        cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
        
        network_config = {
            "version": 2,
            "ethernets": {
                f"eth{interface_index}": {
                    "addresses": [f"{ip_address}/{cidr}"],
                    "gateway4": gateway,
                    "nameservers": {
                        "addresses": ["8.8.8.8", "8.8.4.4"]
                    }
                }
            }
        }
        
        return network_config

    def _apply_cloud_init_config(self, proxmox, node, vm_id, network_config):
        """
        Apply cloud-init network configuration to VM
        """
        try:
            import yaml
            
            # Convert network config to YAML
            network_yaml = yaml.dump(network_config, default_flow_style=False)
            
            # Apply cloud-init network configuration
            cloud_init_data = {
                "cipassword": "temp-password-123",  # Temporary password
                "ciuser": "ubuntu",  # Default cloud-init user
                "ipconfig0": "ip=dhcp",  # Management interface
                "nameserver": "8.8.8.8 8.8.4.4",
                "searchdomain": "local"
            }
            
            # This would require more advanced cloud-init integration
            # For now, we'll return False to try other methods
            return {"success": False, "message": "Cloud-init not fully implemented"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _configure_via_guest_agent(self, proxmox, node, vm_id, bridge_config, interface_index):
        """
        Configure network interface via QEMU guest agent
        """
        try:
            ip_address = bridge_config["ip"]
            netmask = bridge_config["netmask"]
            gateway = bridge_config["gateway"]
            
            # Convert netmask to CIDR
            import ipaddress
            cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
            
            # Wait a bit more for guest agent to be ready
            time.sleep(15)
            
            # Try to execute network configuration commands via guest agent
            commands = [
                f"ip addr add {ip_address}/{cidr} dev eth{interface_index}",
                f"ip link set eth{interface_index} up",
                f"ip route add default via {gateway} dev eth{interface_index} metric 100"
            ]
            
            for cmd in commands:
                try:
                    # Execute command via guest agent
                    result = proxmox.nodes(node).qemu(vm_id).agent.exec.post(
                        command=cmd.split()[0],
                        **{"input-data": cmd}
                    )
                    logger.info(f"Executed via guest agent: {cmd}")
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Guest agent command failed: {cmd} - {e}")
                    return {"success": False, "message": str(e)}
            
            return {"success": True, "message": "Network configured via guest agent"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _generate_network_config_script(self, bridge_config, interface_index):
        """
        Generate a script that can be run inside the VM to configure the network interface
        """
        ip_address = bridge_config["ip"]
        netmask = bridge_config["netmask"]
        gateway = bridge_config["gateway"]
        
        # Convert netmask to CIDR
        import ipaddress
        cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
        
        script = f"""#!/bin/bash
# Network configuration script for eth{interface_index}
# Generated by Katana Proxmox Manager

echo "Configuring network interface eth{interface_index}..."

# Add IP address to interface
sudo ip addr add {ip_address}/{cidr} dev eth{interface_index}

# Bring interface up
sudo ip link set eth{interface_index} up

# Add route to gateway (with higher metric to avoid conflicts)
sudo ip route add default via {gateway} dev eth{interface_index} metric 100

# Verify configuration
echo "Network configuration applied:"
ip addr show eth{interface_index}
ip route show dev eth{interface_index}

echo "Configuration complete for eth{interface_index}"
"""
        
        return script

    def _configure_vm_via_ssh(self, bridge_results, vm_id, vm_name):
        """
        Configure VM network interfaces via SSH with policy-based routing
        """
        try:
            import subprocess
            import time
            
            # Get management interface IP from Proxmox
            management_ip = self._get_vm_management_ip(vm_id)
            if not management_ip:
                return {"success": False, "error": "Could not determine VM management IP for SSH"}
            
            logger.info(f"Found VM management IP: {management_ip}")
            
            # Prepare custom networks for configuration
            custom_networks = []
            for bridge in bridge_results:
                if bridge["type"] != "management":
                    custom_networks.append(bridge)
            
            if not custom_networks:
                return {"success": True, "message": "No custom networks to configure"}
            
            # Test SSH connectivity before proceeding
            if not self._test_ssh_connectivity(management_ip):
                return {"success": False, "error": f"SSH connection failed to {management_ip}"}
            
            # Generate and execute simple routing configuration
            logger.info(f"Configuring policy-based routing on {management_ip}...")
            
            # Use direct ip commands instead of netplan for reliability
            success = self._configure_direct_routing(management_ip, custom_networks)
            
            if success:
                return {
                    "success": True, 
                    "message": f"Policy-based routing configured successfully on {management_ip}",
                    "management_ip": management_ip,
                    "custom_networks": custom_networks
                }
            else:
                return {
                    "success": False, 
                    "error": f"Failed to configure routing on {management_ip}"
                }
            
        except Exception as e:
            logger.error(f"SSH configuration failed: {e}")
            return {"success": False, "error": str(e)}

    def _get_vm_management_ip(self, vm_id):
        """
        Get the VM's management interface IP address from Proxmox
        """
        try:
            # Get cluster info to connect to Proxmox
            clusters = mongoUtils.index(self.proxmox_collection)
            if not clusters:
                logger.error("No Proxmox clusters found")
                return None
            
            cluster = clusters[0]  # Use first available cluster
            conn_result = self._get_proxmox_connection(cluster)
            if not conn_result["success"]:
                logger.error(f"Failed to connect to Proxmox: {conn_result['message']}")
                return None
            
            proxmox = conn_result["connection"]
            node = cluster["node"]
            
            # Wait for VM to boot and get IP via guest agent
            max_attempts = 12  # 2 minutes with 10-second intervals
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Attempting to get VM IP (attempt {attempt + 1}/{max_attempts})...")
                    
                    # Try to get IP from guest agent
                    network_info = proxmox.nodes(node).qemu(vm_id).agent.get("network-get-interfaces")
                    
                    if network_info:
                        # Parse network interfaces to find management IP
                        for interface in network_info.get('result', []):
                            if_name = interface.get('name', '')
                            
                            # Look for eth0 (management interface)
                            if if_name == 'eth0':
                                ip_addresses = interface.get('ip-addresses', [])
                                for ip_info in ip_addresses:
                                    ip = ip_info.get('ip-address')
                                    ip_type = ip_info.get('ip-address-type')
                                    
                                    # Get IPv4 address that's not loopback
                                    if ip and ip_type == 'ipv4' and not ip.startswith('127.'):
                                        logger.info(f"Found management IP via guest agent: {ip}")
                                        return ip
                    
                    logger.info(f"VM guest agent not ready yet, waiting...")
                    time.sleep(10)
                    
                except Exception as e:
                    logger.info(f"Guest agent query failed (attempt {attempt + 1}): {e}")
                    time.sleep(10)
                    continue
            
            # Fallback: Try to get IP from DHCP lease or ARP table
            logger.info("Guest agent method failed, trying alternative methods...")
            
            # Method 2: Check common DHCP ranges based on your network
            management_ranges = [
                "10.160.101",  # Your mentioned range
                "10.160.100", 
                "192.168.1",   # Common ranges
                "10.0.0"
            ]
            
            for base_ip in management_ranges:
                for i in range(50, 200):  # Check broader range
                    test_ip = f"{base_ip}.{i}"
                    
                    # Quick ping test
                    try:
                        result = subprocess.run(['ping', '-c', '1', '-W', '2', test_ip], 
                                              capture_output=True, timeout=5)
                        if result.returncode == 0:
                            # IP responds to ping, test if it's our VM
                            if self._test_ssh_connectivity(test_ip, quick_test=True):
                                logger.info(f"Found VM IP via network scan: {test_ip}")
                                return test_ip
                    except:
                        continue
            
            logger.error("Could not determine VM management IP address")
            return None
            
        except Exception as e:
            logger.error(f"Error getting VM IP: {e}")
            return None

    def _test_ssh_connectivity(self, ip_address, quick_test=False):
        """
        Test SSH connectivity to a given IP address
        """
        try:
            import subprocess
            
            timeout = 5 if quick_test else 15
            
            cmd = ["ssh", "-o", f"ConnectTimeout={timeout}", "-o", "StrictHostKeyChecking=no", 
                   "-o", "BatchMode=yes", f"ubuntu@{ip_address}", "echo", "test"]
            
            result = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
            
            if result.returncode == 0:
                if not quick_test:
                    logger.info(f"SSH connectivity confirmed to {ip_address}")
                return True
            else:
                if not quick_test:
                    logger.warning(f"SSH test failed to {ip_address}: {result.stderr.decode()}")
                return False
                
        except Exception as e:
            if not quick_test:
                logger.warning(f"SSH test exception for {ip_address}: {e}")
            return False

    def _generate_ssh_netplan_script(self, custom_networks):
        """
        Generate netplan configuration for SSH deployment
        """
        config = """network:
  version: 2
  routing-policy:"""
        
        # Add routing policies
        for bridge in custom_networks:
            table_id = 100 + bridge["index"]
            config += f"""
    - from: {bridge['ip']}/32
      table: {table_id}"""
        
        config += """
  ethernets:
    eth0:
      dhcp4: true
      set-name: "eth0\""""
        
        # Add custom interfaces
        for bridge in custom_networks:
            interface = f"eth{bridge['index']}"
            ip = bridge['ip']
            netmask = bridge['netmask']
            gateway = bridge['gateway']
            table_id = 100 + bridge["index"]
            
            # Convert netmask to CIDR
            import ipaddress
            cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
            
            config += f"""
    {interface}:
      addresses:
        - {ip}/{cidr}
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
        search: [local]
      routes:
        - to: 0.0.0.0/0
          via: {gateway}
          table: {table_id}
      set-name: "{interface}\""""
        
        return config

    def _generate_ssh_routing_commands(self, custom_networks):
        """
        Generate routing commands for SSH execution
        """
        commands = []
        
        for bridge in custom_networks:
            table_id = 100 + bridge["index"]
            ip = bridge['ip']
            gateway = bridge['gateway']
            
            commands.append(f"sudo ip rule add from {ip}/32 table {table_id} 2>/dev/null || true")
            commands.append(f"sudo ip route add default via {gateway} table {table_id} 2>/dev/null || true")
        
        return " && ".join(commands)

    def _configure_direct_routing(self, management_ip, custom_networks):
        """
        Configure policy-based routing using direct ip commands (more reliable than netplan)
        """
        try:
            logger.info(f"Configuring direct routing for {len(custom_networks)} custom networks")
            
            # Step 1: Configure IP addresses on custom interfaces
            for bridge in custom_networks:
                interface = f"eth{bridge['index']}"
                ip = bridge['ip']
                netmask = bridge['netmask']
                
                # Convert netmask to CIDR
                import ipaddress
                cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
                
                # Add IP to interface
                cmd = f"sudo ip addr add {ip}/{cidr} dev {interface}"
                result = self._execute_ssh_command(management_ip, cmd)
                if not result:
                    logger.error(f"Failed to add IP {ip} to {interface}")
                    return False
                
                # Bring interface up
                cmd = f"sudo ip link set {interface} up"
                result = self._execute_ssh_command(management_ip, cmd)
                if not result:
                    logger.error(f"Failed to bring up {interface}")
                    return False
                
                logger.info(f"Configured {interface} with {ip}/{cidr}")
            
            # Step 2: Create routing tables and rules
            for bridge in custom_networks:
                table_id = 100 + bridge['index']
                ip = bridge['ip']
                gateway = bridge['gateway']
                interface = f"eth{bridge['index']}"
                
                # Add routing rule for source IP
                cmd = f"sudo ip rule add from {ip}/32 table {table_id}"
                result = self._execute_ssh_command(management_ip, cmd)
                if result:
                    logger.info(f"Added routing rule for {ip} -> table {table_id}")
                
                # Add default route in custom table
                cmd = f"sudo ip route add default via {gateway} dev {interface} table {table_id}"
                result = self._execute_ssh_command(management_ip, cmd)
                if result:
                    logger.info(f"Added default route via {gateway} in table {table_id}")
                
                # Add local network route in custom table
                netmask = bridge['netmask']
                cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
                network = ipaddress.IPv4Network(f"{ip}/{cidr}", strict=False).network_address
                cmd = f"sudo ip route add {network}/{cidr} dev {interface} src {ip} table {table_id}"
                result = self._execute_ssh_command(management_ip, cmd)
                if result:
                    logger.info(f"Added local network route {network}/{cidr} in table {table_id}")
            
            # Step 3: Verify configuration
            logger.info("Verifying routing configuration...")
            
            # Check routing rules
            result = self._execute_ssh_command(management_ip, "ip rule show", capture_output=True)
            if result and result.get('stdout'):
                logger.info(f"Routing rules:\n{result['stdout']}")
            
            # Check routing tables
            for bridge in custom_networks:
                table_id = 100 + bridge['index']
                result = self._execute_ssh_command(management_ip, f"ip route show table {table_id}", capture_output=True)
                if result and result.get('stdout'):
                    logger.info(f"Routing table {table_id}:\n{result['stdout']}")
            
            # Step 4: Make configuration persistent
            self._make_routing_persistent(management_ip, custom_networks)
            
            logger.info("Direct routing configuration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Direct routing configuration failed: {e}")
            return False

    def _execute_ssh_command(self, ip_address, command, capture_output=False):
        """
        Execute a single SSH command and return result
        """
        try:
            ssh_cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no",
                       f"ubuntu@{ip_address}", command]
            
            result = subprocess.run(ssh_cmd, capture_output=True, timeout=30, text=True)
            
            if result.returncode == 0:
                if capture_output:
                    return {
                        'success': True,
                        'stdout': result.stdout.strip(),
                        'stderr': result.stderr.strip()
                    }
                return True
            else:
                logger.warning(f"SSH command failed: {command} -> {result.stderr}")
                if capture_output:
                    return {
                        'success': False,
                        'stdout': result.stdout.strip(),
                        'stderr': result.stderr.strip()
                    }
                return False
                
        except Exception as e:
            logger.error(f"SSH command execution failed: {command} -> {e}")
            return False

    def _make_routing_persistent(self, management_ip, custom_networks):
        """
        Make the routing configuration persistent across reboots
        """
        try:
            # Create a startup script that applies the routing configuration
            script_content = """#!/bin/bash
# Auto-generated routing configuration script
# Applied at boot to maintain policy-based routing

# Wait for network interfaces to be ready
sleep 5

"""
            
            for bridge in custom_networks:
                interface = f"eth{bridge['index']}"
                ip = bridge['ip']
                netmask = bridge['netmask']
                gateway = bridge['gateway']
                table_id = 100 + bridge['index']
                
                # Convert netmask to CIDR
                import ipaddress
                cidr = ipaddress.IPv4Network(f"0.0.0.0/{netmask}", strict=False).prefixlen
                network = ipaddress.IPv4Network(f"{ip}/{cidr}", strict=False).network_address
                
                script_content += f"""
# Configure {interface}
ip addr add {ip}/{cidr} dev {interface} 2>/dev/null || true
ip link set {interface} up
ip rule add from {ip}/32 table {table_id} 2>/dev/null || true
ip route add default via {gateway} dev {interface} table {table_id} 2>/dev/null || true
ip route add {network}/{cidr} dev {interface} src {ip} table {table_id} 2>/dev/null || true

echo "Configured {interface}: {ip}/{cidr} via {gateway} (table {table_id})"
"""
            
            script_content += """
echo "Policy-based routing configuration applied"
"""
            
            # Write the script to the VM
            script_path = "/usr/local/bin/setup-routing.sh"
            cmd = f"sudo tee {script_path} > /dev/null << 'EOF'\n{script_content}\nEOF"
            result = self._execute_ssh_command(management_ip, cmd)
            
            if result:
                # Make script executable
                self._execute_ssh_command(management_ip, f"sudo chmod +x {script_path}")
                
                # Add to systemd service
                service_content = f"""[Unit]
Description=Custom Policy-based Routing Setup
After=network.target

[Service]
Type=oneshot
ExecStart={script_path}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
                
                cmd = f"sudo tee /etc/systemd/system/setup-routing.service > /dev/null << 'EOF'\n{service_content}\nEOF"
                result = self._execute_ssh_command(management_ip, cmd)
                
                if result:
                    # Enable the service
                    self._execute_ssh_command(management_ip, "sudo systemctl daemon-reload")
                    self._execute_ssh_command(management_ip, "sudo systemctl enable setup-routing.service")
                    logger.info("Made routing configuration persistent via systemd service")
                
        except Exception as e:
            logger.warning(f"Failed to make routing persistent: {e}")