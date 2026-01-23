#!/usr/bin/env python3
"""
Flask API endpoints for 5G Stack Deployment

Integrates Open5GS and UERANSIM deployment into the existing katana-nbi system.
"""

from flask import Blueprint, request, jsonify
from flask_classful import FlaskView, route
import os
import json
import logging
from pathlib import Path
from threading import Thread
from datetime import datetime
import yaml

# Import the 5G deployment manager
from .five_g_deployment import FiveGDeploymentManager


logger = logging.getLogger(__name__)


class FiveGStackView(FlaskView):
    """REST API endpoints for 5G stack management."""
    
    route_prefix = "/api/"
    route_base = '/5g/stack'
    
    def __init__(self):
        """Initialize the view."""
        self.active_deployments = {}
        self.deployment_logs = {}
    
    @route('/deploy', methods=['POST'])
    def deploy_5g_stack(self):
        """
        Deploy Open5GS and UERANSIM stack.
        
        Request body:
        {
            "config_file": "path/to/config.yaml" or "config_dict": {...},
            "vm_mapping": {
                "open5gs_vm": "sofiaDemo1",
                "ueransim_vm": "sofiaDemo2"
            },
            "ssh_credentials": {
                "username": "ubuntu",
                "password": "ubuntu"
            }
        }
        """
        try:
            data = request.get_json()
            
            # Get configuration
            if 'config_file' in data:
                config_file = data['config_file']
            elif 'config_dict' in data:
                config_file = self._save_config_to_file(data['config_dict'])
            else:
                return jsonify({'error': 'config_file or config_dict required'}), 400
            
            # Validate file exists
            if not os.path.exists(config_file):
                return jsonify({'error': f'Configuration file not found: {config_file}'}), 404
            
            # Create deployment manager
            deployment_id = datetime.now().strftime('%Y%m%d_%H%M%S')
            manager = FiveGDeploymentManager(config_file)
            
            # Store Proxmox credentials for later use
            proxmox_creds = data.get('proxmox_credentials', {})
            
            # Start deployment in background thread
            thread = Thread(
                target=self._run_deployment,
                args=(deployment_id, manager, data.get('ssh_credentials', {}), proxmox_creds)
            )
            thread.daemon = True
            thread.start()
            
            self.active_deployments[deployment_id] = {
                'status': 'in_progress',
                'config_file': config_file,
                'start_time': datetime.now().isoformat(),
                'thread': thread
            }
            
            return jsonify({
                'deployment_id': deployment_id,
                'status': 'deployment_started',
                'message': 'Deployment initiated in background'
            }), 202
        
        except Exception as e:
            logger.error(f"Deployment endpoint error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @route('/status/<deployment_id>', methods=['GET'])
    def get_deployment_status(self, deployment_id):
        """Get status of a specific deployment."""
        try:
            if deployment_id not in self.active_deployments:
                # Try to load from log file
                log_file = f"deployment_{deployment_id}.json"
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        logs = json.load(f)
                    return jsonify({
                        'deployment_id': deployment_id,
                        'status': 'completed',
                        'logs': logs
                    }), 200
                else:
                    return jsonify({'error': 'Deployment not found'}), 404
            
            deployment = self.active_deployments[deployment_id]
            
            return jsonify({
                'deployment_id': deployment_id,
                'status': deployment['status'],
                'start_time': deployment['start_time'],
                'is_running': deployment.get('thread', {}).is_alive() if deployment.get('thread') else False
            }), 200
        
        except Exception as e:
            logger.error(f"Status endpoint error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @route('/list', methods=['GET'])
    def list_deployments(self):
        """List all active deployments."""
        try:
            deployments = []
            for dep_id, dep_info in self.active_deployments.items():
                deployments.append({
                    'id': dep_id,
                    'status': dep_info['status'],
                    'start_time': dep_info['start_time'],
                    'config_file': dep_info['config_file']
                })
            
            return jsonify({'deployments': deployments}), 200
        
        except Exception as e:
            logger.error(f"List endpoint error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @route('/config/template', methods=['GET'])
    def get_config_template(self):
        """Get a template for 5G deployment configuration."""
        template = {
            "five_g_deployment": {
                "open5gs_core": {
                    "enabled": True,
                    "vm_name": "sofiaDemo1",
                    "configuration": {
                        "plmn": {
                            "mcc": 999,
                            "mnc": 70
                        },
                        "interfaces": {
                            "nrf_sbi": {
                                "address": "192.168.10.52",
                                "port": 7777
                            },
                            "amf_ngap": {
                                "address": "192.168.10.52",
                                "port": 38412
                            },
                            "upf_gtpu": {
                                "address": "192.168.10.52",
                                "port": 2152
                            },
                            "upf_pfcp": {
                                "address": "192.168.10.52",
                                "port": 8805
                            }
                        },
                        "subscribers": [
                            {
                                "imsi": "999700000000001",
                                "key": "465B5CE8B199B49FAA5F0A2EE238A6BC",
                                "opc": "E8ED289DEBA952E4283B54E88E6183CA",
                                "amf": "8000",
                                "slice_sst": 1,
                                "slice_sd": "0xffffff",
                                "apn": "internet"
                            }
                        ],
                        "upf_subnets": [
                            {
                                "name": "default",
                                "address": "10.45.0.1/16"
                            }
                        ]
                    }
                },
                "ueransim": {
                    "enabled": True,
                    "vm_name": "sofiaDemo2",
                    "install_type": "gnb_and_ue",
                    "configuration": {
                        "plmn": {
                            "mcc": 999,
                            "mnc": 70
                        },
                        "gnb": {
                            "name": "gnb-1",
                            "id": 1,
                            "interfaces": {
                                "link_ip": "192.168.20.52",
                                "ngap_ip": "192.168.20.52",
                                "gtp_ip": "192.168.20.52"
                            },
                            "amf_configs": [
                                {
                                    "ip": "192.168.10.52",
                                    "port": 38412,
                                    "name": "amf-1"
                                }
                            ]
                        },
                        "ue": {
                            "supi": "999700000000001",
                            "imei": "356938035643803",
                            "key": "465B5CE8B199B49FAA5F0A2EE238A6BC",
                            "opc": "E8ED289DEBA952E4283B54E88E6183CA",
                            "amf": "8000"
                        }
                    }
                }
            }
        }
        
        return jsonify(template), 200
    
    @route('/config/validate', methods=['POST'])
    def validate_config(self):
        """Validate 5G deployment configuration."""
        try:
            data = request.get_json()
            
            if 'config' not in data:
                return jsonify({'error': 'config field required'}), 400
            
            config = data['config']
            errors = []
            warnings = []
            
            # Validate Open5GS config
            open5gs = config.get('five_g_deployment', {}).get('open5gs_core', {})
            if open5gs.get('enabled'):
                # Check PLMN
                plmn = open5gs.get('configuration', {}).get('plmn', {})
                if not plmn.get('mcc') or not plmn.get('mnc'):
                    errors.append("Open5GS PLMN configuration incomplete")
                
                # Check subscribers
                subscribers = open5gs.get('configuration', {}).get('subscribers', [])
                if not subscribers:
                    warnings.append("No subscribers configured for Open5GS")
            
            # Validate UERANSIM config
            ueransim = config.get('five_g_deployment', {}).get('ueransim', {})
            if ueransim.get('enabled'):
                # Check gNB config
                gnb = ueransim.get('configuration', {}).get('gnb', {})
                interfaces = gnb.get('interfaces', {})
                
                # NGAP IP is required (can be empty string for auto-detect or an actual IP)
                if 'ngap_ip' not in interfaces:
                    errors.append("UERANSIM gNB NGAP IP not configured (use empty string '' for auto-detect)")
                
                if not gnb.get('amf_configs'):
                    errors.append("UERANSIM gNB AMF configuration missing")
            
            return jsonify({
                'valid': len(errors) == 0,
                'errors': errors,
                'warnings': warnings
            }), 200
        
        except Exception as e:
            logger.error(f"Validation endpoint error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @route('/logs/<deployment_id>', methods=['GET'])
    def get_deployment_logs(self, deployment_id):
        """Get logs from a deployment."""
        try:
            log_file = f"deployment_{deployment_id}.json"
            
            if not os.path.exists(log_file):
                return jsonify({'error': 'Log file not found'}), 404
            
            with open(log_file, 'r') as f:
                logs = json.load(f)
            
            return jsonify({
                'deployment_id': deployment_id,
                'logs': logs,
                'log_count': len(logs)
            }), 200
        
        except Exception as e:
            logger.error(f"Logs endpoint error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    def _save_config_to_file(self, config_dict):
        """Save configuration dictionary to a YAML file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        config_file = f"5g_config_{timestamp}.yaml"
        
        with open(config_file, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False)
        
        logger.info(f"Configuration saved to {config_file}")
        return config_file
    
    def _run_deployment(self, deployment_id, manager, ssh_creds, proxmox_creds=None):
        """Run deployment in background."""
        try:
            # Store Proxmox credentials on the manager for IP detection
            if proxmox_creds:
                manager.proxmox_host = proxmox_creds.get('host', '10.160.100.11')
                manager.proxmox_user = proxmox_creds.get('user', 'root@pam')
                manager.proxmox_password = proxmox_creds.get('password')
            
            # Update SSH credentials if provided
            if ssh_creds:
                for vm_spec in manager.config.get('five_g_deployment', {}).values():
                    if isinstance(vm_spec, dict) and 'vm_name' in vm_spec:
                        vm_spec['ssh_credentials'] = ssh_creds
            
            # Execute deployment
            success = manager.deploy()
            
            # Update status
            self.active_deployments[deployment_id]['status'] = 'completed' if success else 'failed'
            self.active_deployments[deployment_id]['result'] = 'success' if success else 'failure'
            
            # Copy logs to permanent storage
            manager.save_deployment_log(f"deployment_{deployment_id}.json")
            
            logger.info(f"Deployment {deployment_id} completed with status: {'SUCCESS' if success else 'FAILURE'}")
        
        except Exception as e:
            logger.error(f"Background deployment failed: {str(e)}")
            self.active_deployments[deployment_id]['status'] = 'failed'
            self.active_deployments[deployment_id]['error'] = str(e)
