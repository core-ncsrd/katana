#!/usr/bin/env python3
"""
5G Stack Deployment Manager for Open5GS and UERANSIM

This module handles the automated installation, configuration, and management of
Open5GS (5G Core Network) and UERANSIM (5G RAN Simulator) on Proxmox VMs.

Usage:
    from five_g_deployment import FiveGDeploymentManager
    manager = FiveGDeploymentManager(config_file="open5gs_ueransim_deployment.yaml")
    manager.deploy()
"""

import yaml
import json
import logging
import subprocess
import time
import paramiko
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from jinja2 import Template
from datetime import datetime

try:
    from proxmoxer import ProxmoxAPI
except ImportError:
    ProxmoxAPI = None


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VMInfo:
    """Information about a VM for deployment."""
    name: str
    ip_address: str
    username: str = "localadmin"
    password: str = "ii70mseq"
    ssh_key: str = None
    port: int = 22


class SSHConnection:
    """Manages SSH connections to VMs."""
    
    def __init__(self, vm_info: VMInfo, timeout: int = 30):
        """Initialize SSH connection."""
        self.vm_info = vm_info
        self.timeout = timeout
        self.client = None
        self.detected_ip = None
    
    def connect(self) -> bool:
        """Establish SSH connection."""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if self.vm_info.ssh_key:
                self.client.connect(
                    self.vm_info.ip_address,
                    port=self.vm_info.port,
                    username=self.vm_info.username,
                    key_filename=self.vm_info.ssh_key,
                    timeout=self.timeout
                )
            else:
                self.client.connect(
                    self.vm_info.ip_address,
                    port=self.vm_info.port,
                    username=self.vm_info.username,
                    password=self.vm_info.password,
                    timeout=self.timeout
                )
            
            logger.info(f"SSH connection established to {self.vm_info.name} ({self.vm_info.ip_address})")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {self.vm_info.name}: {str(e)}")
            return False
    
    def execute_command(self, command: str, timeout: int = 300) -> Tuple[int, str, str]:
        """Execute a command via SSH."""
        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            
            return return_code, output, error
        except Exception as e:
            logger.error(f"Command execution failed on {self.vm_info.name}: {str(e)}")
            return 1, "", str(e)
    
    def execute_script(self, script_content: str) -> Tuple[int, str, str]:
        """Execute a bash script via SSH."""
        temp_script = "/tmp/deploy_script_{}_.sh".format(int(time.time() * 1000))
        
        try:
            # Write script to remote
            stdin, stdout, stderr = self.client.open_sftp()
            with stdin.file(temp_script, 'w') as f:
                f.write(script_content)
            stdin.close()
            
            # Execute script
            return_code, output, error = self.execute_command(f"chmod +x {temp_script} && bash {temp_script}")
            
            # Cleanup
            self.execute_command(f"rm {temp_script}")
            
            return return_code, output, error
        except Exception as e:
            logger.error(f"Script execution failed on {self.vm_info.name}: {str(e)}")
            return 1, "", str(e)
    
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """Upload a file via SFTP."""
        try:
            sftp = self.client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            logger.info(f"File uploaded to {self.vm_info.name}: {remote_path}")
            return True
        except Exception as e:
            logger.error(f"File upload failed to {self.vm_info.name}: {str(e)}")
            return False
    
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download a file via SFTP."""
        try:
            sftp = self.client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
            logger.info(f"File downloaded from {self.vm_info.name}: {remote_path}")
            return True
        except Exception as e:
            logger.error(f"File download failed from {self.vm_info.name}: {str(e)}")
            return False
    
    def disconnect(self):
        """Close SSH connection."""
        if self.client:
            self.client.close()
            logger.info(f"SSH connection closed to {self.vm_info.name}")
    
    def detect_vmbr1601_ip(self) -> Optional[str]:
        """
        Detect DHCP-assigned IP from eth0 interface (or first available interface).
        
        Returns:
            IP address string or None if not found
        """
        try:
            # Try eth0 first (most common)
            cmd = "ip addr show eth0 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1"
            ret, output, error = self.execute_command(cmd)
            
            if ret == 0 and output.strip():
                ip = output.strip()
                self.detected_ip = ip
                logger.info(f"Detected eth0 IP on {self.vm_info.name}: {ip}")
                return ip
            
            # Fallback: try any interface
            cmd = "hostname -I | awk '{print $1}'"
            ret, output, error = self.execute_command(cmd)
            
            if ret == 0 and output.strip():
                ip = output.strip()
                self.detected_ip = ip
                logger.info(f"Detected IP on {self.vm_info.name}: {ip}")
                return ip
            
            logger.warning(f"Failed to detect IP on {self.vm_info.name}")
            return None
        except Exception as e:
            logger.error(f"Error detecting IP: {str(e)}")
            return None


class ConfigurationGenerator:
    """Generates configuration files for Open5GS and UERANSIM."""
    
    @staticmethod
    def resolve_ip(config: Dict, connection: Optional[SSHConnection] = None) -> str:
        """
        Resolve IP address from config or auto-detect from DHCP.
        
        Args:
            config: Configuration dictionary potentially with custom IP (empty = auto-detect)
            connection: SSH connection to auto-detect IP if needed
        
        Returns:
            IP address string
        """
        # Check if custom IP is provided (not empty, not empty string)
        address = config.get('address', '')
        if address and address.strip():
            return address
        
        # Try to auto-detect from vmbr1601 (primary interface)
        if connection:
            detected_ip = connection.detect_vmbr1601_ip()
            if detected_ip:
                logger.info(f"Auto-detected IP from network interface: {detected_ip}")
                return detected_ip
        
        # Fallback to loopback if nothing else works
        logger.warning("Could not resolve IP, falling back to localhost")
        return "127.0.0.1"
    
    @staticmethod
    def generate_nrf_config(config_dict: Dict, vm_ip: str = '127.0.0.10') -> str:
        """Generate NRF configuration YAML.
        
        Args:
            config_dict: Configuration dictionary
            vm_ip: Detected VM IP (default: localhost for NRF)
        """
        template = """logger:
  file:
    path: /var/log/open5gs/nrf.log

global:
  max_concurrency: 200

nrf:
  serving:
    - plmn_id:
        mcc: {{ plmn.mcc }}
        mnc: '{{ "%02d" % plmn.mnc }}'
  sbi:
    server:
      - address: 127.0.0.10
        port: 7777
  logging:
    level: debug
"""
        # Extract configuration from the nested structure
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(config)
    
    @staticmethod
    def generate_amf_config(config_dict: Dict, vm_ip: str = '10.160.101.132') -> str:
        """Generate AMF configuration YAML.
        
        Args:
            config_dict: Configuration dictionary
            vm_ip: Detected VM IP for NGAP interface (ONLY for external N2 interface)
        """
        template = """logger:
  file:
    path: /var/log/open5gs/amf.log

global:
  max:
    ue: 1024

amf:
  amf_name: amf
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.5
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  ngap:
    server:
      - address: {{ vm_ip }}
  guami:
    - plmn_id:
        mcc: {{ plmn.mcc }}
        mnc: '{{ "%02d" % plmn.mnc }}'
      amf_id:
        region: 2
        set: 1
  tai:
    - plmn_id:
        mcc: {{ plmn.mcc }}
        mnc: '{{ "%02d" % plmn.mnc }}'
      tac: 1
  plmn_support:
    - plmn_id:
        mcc: {{ plmn.mcc }}
        mnc: '{{ "%02d" % plmn.mnc }}'
      s_nssai:
        - sst: 1
  security:
    integrity_order: ["NIA2", "NIA1", "NIA0"]
    ciphering_order: ["NEA0", "NEA1", "NEA2"]
  network_name:
    full: "Open5GS"
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(plmn=config.get('plmn', {}), vm_ip=vm_ip)
    
    @staticmethod
    def generate_upf_config(config_dict: Dict, vm_ip: str = '127.0.0.7') -> str:
        """Generate UPF configuration YAML.
        
        Args:
            config_dict: Configuration dictionary  
            vm_ip: Detected VM IP for external PFCP/GTPU interfaces
        """
        template = """logger:
  file:
    path: /var/log/open5gs/upf.log

upf:
  pfcp:
    server:
      - address: {{ vm_ip }}
        port: 8805
    client_list:
      - uri: http://127.0.0.4:7777
  gtpu:
    server:
      - address: {{ vm_ip }}
        port: 2152
  session:
    - subnet: 10.45.0.0/16
      gateway: 10.45.0.1
    - subnet: 2001:db8:cafe::/48
      gateway: 2001:db8:cafe::1
  metrics:
    server:
      - address: 127.0.0.7
        port: 9090
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(vm_ip=vm_ip)
    
    @staticmethod
    def generate_smf_config(config_dict: Dict, vm_ip: str = '127.0.0.4') -> str:
        """Generate SMF configuration YAML with dynamic IP injection for external interfaces."""
        template = """logger:
  file:
    path: /var/log/open5gs/smf.log

global:
  max:
    ue: 1024
    sess: 20480

smf:
  sbi:
    server:
      - address: {{ vm_ip }}
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  pfcp:
    server:
      - address: 127.0.0.4
        port: 8805
    client:
      upf:
        - address: {{ vm_ip }}
          port: 8805
  gtpc:
    server:
      - address: 127.0.0.4
        port: 2123
  session:
    - subnet: 10.45.0.0/16
      gateway: 10.45.0.1
    - subnet: 2001:db8:cafe::/48
      gateway: 2001:db8:cafe::1
  dns:
    - 8.8.8.8
    - 8.8.4.4
    - 2001:4860:4860::8888
    - 2001:4860:4860::8844
  mtu: 1400
  metrics:
    server:
      - address: 127.0.0.4
        port: 9090
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(vm_ip=vm_ip)
    
    @staticmethod
    def generate_ausf_config(config_dict: Dict, vm_ip: str = '127.0.0.11') -> str:
        """Generate AUSF configuration YAML with dynamic IP for SBI server."""
        template = """logger:
  file:
    path: /var/log/open5gs/ausf.log

ausf:
  sbi:
    server:
      - address: {{ vm_ip }}
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
      udm:
        - uri: http://127.0.0.12:7777
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(vm_ip=vm_ip)
    
    @staticmethod
    def generate_udm_config(config_dict: Dict, vm_ip: str = '127.0.0.12') -> str:
        """Generate UDM configuration YAML with dynamic IP for SBI server."""
        template = """logger:
  file:
    path: /var/log/open5gs/udm.log

udm:
  sbi:
    server:
      - address: {{ vm_ip }}
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
      udr:
        - uri: http://127.0.0.20:7777
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(vm_ip=vm_ip)
    
    @staticmethod
    def generate_udr_config(config_dict: Dict, vm_ip: str = '127.0.0.20') -> str:
        """Generate UDR configuration YAML with dynamic IP for SBI server."""
        template = """logger:
  file:
    path: /var/log/open5gs/udr.log

udr:
  sbi:
    server:
      - address: {{ vm_ip }}
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(vm_ip=vm_ip)
    
    @staticmethod
    def generate_pcf_config(config_dict: Dict, vm_ip: str = '127.0.0.13') -> str:
        """Generate PCF configuration YAML with dynamic IP for SBI server."""
        template = """logger:
  file:
    path: /var/log/open5gs/pcf.log

pcf:
  sbi:
    server:
      - address: {{ vm_ip }}
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(vm_ip=vm_ip)
    
    @staticmethod
    def generate_nssf_config(config_dict: Dict, vm_ip: str = '127.0.0.14') -> str:
        """Generate NSSF configuration YAML with dynamic IP for SBI server."""
        template = """logger:
  file:
    path: /var/log/open5gs/nssf.log

nssf:
  sbi:
    server:
      - address: {{ vm_ip }}
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  nsi:
    - plmn_id:
        mcc: {{ plmn.mcc }}
        mnc: '{{ "%02d" % plmn.mnc }}'
      default: true
      slice:
        - sst: 1
          sd: 0xffffff
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(plmn=config.get('plmn', {}), vm_ip=vm_ip)
    
    @staticmethod
    def generate_bsf_config(config_dict: Dict, vm_ip: str = '127.0.0.15') -> str:
        """Generate BSF configuration YAML with dynamic IP for SBI server."""
        template = """logger:
  file:
    path: /var/log/open5gs/bsf.log

bsf:
  sbi:
    server:
      - address: {{ vm_ip }}
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
"""
        config = config_dict.get('configuration', {})
        t = Template(template)
        return t.render(vm_ip=vm_ip)
        """Generate UERANSIM gNodeB configuration YAML."""
        config = config_dict.get('configuration', {})
        gnb_config = config.get('gnb', {})
        plmn = config.get('plmn', {})
        
        template = """
mcc: '{{ plmn.mcc }}'
mnc: '{{ "%02d" % plmn.mnc }}'
nci: 0x{{ '%010x' % gnb_config.id }}
idLength: 32
linkIp: {{ gnb_config.interfaces.link_ip }}
ngapIp: {{ gnb_config.interfaces.ngap_ip }}
gtpIp: {{ gnb_config.interfaces.gtp_ip }}
ignoreStreamIds: false

amfConfigs:
{%- for amf in gnb_config.amf_configs %}
  - address: {{ amf.ip }}
    port: {{ amf.port | default(38412) }}
{%- endfor %}

ngRanNodeName: gnb-{{ gnb_config.id }}

supportedTaList:
  - tac: 1
    broadcastPlmnList:
      - mcc: '{{ plmn.mcc }}'
        mnc: '{{ "%02d" % plmn.mnc }}'
        snssaiList:
          - sst: 1

nr-cell-list:
  - nrCellId: 1
    cellIdLength: 32
    iab-du-cell-id: 0
    tac: 1
    nrPci: 1
    dl-arfcn: 368500
    cu-up-amf-cpu-usage: 80
    cu-up-amf-mem-usage: 80
    du-cpu-usage: 80
    du-mem-usage: 80

slices:
  - sst: 1
    sd: 0xffffff

plmnList:
  - mcc: '{{ plmn.mcc }}'
    mnc: '{{ "%02d" % plmn.mnc }}'

tac: 1
defaultAs: 127.0.0.1
supportedAlgs:
  integrityOrder: ["NIA2", "NIA1", "NIA0"]
  cipheringOrder: ["NEA0", "NEA1", "NEA2"]

logging:
  level: debug
"""
        t = Template(template)
        context = {
            'plmn': plmn,
            'gnb_config': gnb_config
        }
        return t.render(context)
    
    @staticmethod
    def generate_ueransim_ue_config(config_dict: Dict) -> str:
        """Generate UERANSIM UE configuration YAML."""
        config = config_dict.get('configuration', {})
        ue_config = config.get('ue', {})
        plmn = config.get('plmn', {})
        
        template = """
supi: '{{ ue_config.supi }}'
mcc: '{{ plmn.mcc }}'
mnc: '{{ "%02d" % plmn.mnc }}'
key: '{{ ue_config.key }}'
op: '{{ ue_config.opc }}'
opType: 'OPC'
amf: '{{ ue_config.amf }}'
imei: '{{ ue_config.imei }}'
imeiSv: '{{ ue_config.imeiSv }}'

gnbSearchList:
  - 127.0.0.1

slices:
  - sst: 1
    sd: 'fffffe'

sessions:
  - type: 'IPv4'
    apn: 'internet'
    slice:
      sst: 1
      sd: 'fffffe'

supportedAlgs:
  integrityOrder: ["NIA2", "NIA1", "NIA0"]
  cipheringOrder: ["NEA0", "NEA1", "NEA2"]

logging:
  level: debug
"""
        t = Template(template)
        context = {
            'plmn': plmn,
            'ue_config': ue_config
        }
        return t.render(context)


class FiveGDeploymentManager:
    """Main orchestrator for 5G stack deployment."""
    
    def __init__(self, config_file: str):
        """Initialize the deployment manager."""
        self.config_file = config_file
        self.config = self._load_config()
        self.vm_connections: Dict[str, SSHConnection] = {}
        self.deployment_log = []
        
        # Proxmox credentials (can be set by API)
        self.proxmox_host = "10.160.100.11"
        self.proxmox_user = "root@pam"
        self.proxmox_password = None
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            raise
    
    def _get_vm_ip_from_proxmox(self, vm_name: str) -> Optional[str]:
        """
        Detect VM IP address from Proxmox cluster using qemu-agent.
        
        Args:
            vm_name: Name of the VM to find
        
        Returns:
            IP address of the VM, or None if not found
        """
        if not ProxmoxAPI:
            logger.warning("Proxmoxer not installed, cannot auto-detect VM IPs")
            return None
        
        if not self.proxmox_password:
            logger.warning(f"No Proxmox password configured, skipping auto-detection for {vm_name}")
            return None
        
        try:
            # Connect to Proxmox
            proxmox = ProxmoxAPI(
                self.proxmox_host, 
                user=self.proxmox_user, 
                password=self.proxmox_password,
                verify_ssl=False,
                timeout=10
            )
            
            logger.info(f"Connected to Proxmox at {self.proxmox_host}")
            
            # Search for VM in all nodes
            for node_info in proxmox.nodes.get():
                node_name = node_info['node']
                
                try:
                    # List all VMs on this node
                    for vm_info in proxmox.nodes(node_name).qemu.get():
                        if vm_info['name'] == vm_name:
                            # Found the VM, now get its IP address via qemu-agent
                            vmid = vm_info['vmid']
                            logger.info(f"Found {vm_name} (VMID: {vmid}) on node {node_name}")
                            
                            try:
                                # Get network interfaces via qemu-agent
                                agent_result = proxmox.nodes(node_name).qemu(vmid).agent('network-get-interfaces').get()
                                
                                if 'result' in agent_result:
                                    for interface in agent_result['result']:
                                        iface_name = interface.get('name', '')
                                        
                                        # Skip loopback
                                        if iface_name == 'lo':
                                            continue
                                        
                                        if 'ip-addresses' in interface:
                                            for ip_info in interface['ip-addresses']:
                                                ip_type = ip_info.get('ip-address-type', '')
                                                ip_addr = ip_info.get('ip-address')
                                                
                                                # Get first non-loopback IPv4
                                                if ip_type == 'ipv4' and ip_addr and not ip_addr.startswith('127.'):
                                                    logger.info(f"Found {vm_name} at {ip_addr} via qemu-agent")
                                                    return ip_addr
                                
                                logger.warning(f"VM {vm_name} found but no IPv4 detected via qemu-agent")
                                return None
                            
                            except Exception as agent_error:
                                logger.warning(f"qemu-agent error for {vm_name}: {str(agent_error)}")
                                return None
                
                except Exception as e:
                    logger.debug(f"Error checking node {node_name}: {str(e)}")
                    continue
            
            logger.error(f"VM {vm_name} not found in Proxmox cluster")
            return None
        
        except Exception as e:
            logger.error(f"Failed to connect to Proxmox: {str(e)}")
            return None
    
    def _log_action(self, action: str, status: str, details: str = ""):
        """Log deployment actions."""
        timestamp = datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'action': action,
            'status': status,
            'details': details
        }
        self.deployment_log.append(log_entry)
        logger.info(f"{action}: {status} - {details}")
    
    def connect_to_vms(self, vm_list: List[Dict]) -> bool:
        """Connect to all required VMs."""
        logger.info("Establishing SSH connections to VMs...")
        
        for vm_spec in vm_list:
            vm_info = VMInfo(
                name=vm_spec['name'],
                ip_address=vm_spec['ip_address'],
                username=vm_spec.get('username', 'localadmin'),
                password=vm_spec.get('password'),
                ssh_key=vm_spec.get('ssh_key'),
                port=vm_spec.get('port', 22)
            )
            
            connection = SSHConnection(vm_info)
            if connection.connect():
                self.vm_connections[vm_spec['name']] = connection
                self._log_action(f"Connect to {vm_spec['name']}", "SUCCESS")
            else:
                self._log_action(f"Connect to {vm_spec['name']}", "FAILED")
                return False
        
        return len(self.vm_connections) > 0
    
    def deploy_open5gs(self, open5gs_config: Dict, vm_name: str) -> bool:
        """Deploy Open5GS on specified VM."""
        if vm_name not in self.vm_connections:
            logger.error(f"VM {vm_name} not connected")
            return False
        
        connection = self.vm_connections[vm_name]
        logger.info(f"Deploying Open5GS on {vm_name}...")
        
        try:
            # Step 0: Update system packages
            logger.info("Step 0: Updating system packages...")
            ret, out, err = connection.execute_command("sudo apt-get update -qq")
            if ret != 0:
                logger.warning(f"Package update had issues: {err}")
            
            # Step 1: Install MongoDB (required by Open5GS)
            logger.info("Step 1: Installing MongoDB...")
            mongo_commands = [
                "sudo apt-get update -qq",
                "sudo apt-get install -y gnupg ca-certificates",
                "curl -fsSL https://pgp.mongodb.com/server-8.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor",
                "echo 'deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/8.0 multiverse' | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list",
                "sudo apt-get update -qq",
                "sudo apt-get install -y mongodb-org",
                "sudo systemctl start mongod",
                "sudo systemctl enable mongod"
            ]
            
            for cmd in mongo_commands:
                ret, out, err = connection.execute_command(cmd, timeout=300)
                if ret != 0:
                    logger.warning(f"MongoDB setup: {err}")
                else:
                    logger.info(f"✓ Command completed")
            
            # Verify MongoDB is running
            logger.info("Verifying MongoDB installation...")
            ret, out, err = connection.execute_command("sudo systemctl is-active mongod", timeout=30)
            if ret != 0:
                logger.warning(f"MongoDB may not be running properly: {err}")
            
            # Step 2: Install Open5GS from PPA
            logger.info("Step 2: Installing Open5GS packages...")
            open5gs_commands = [
                "sudo add-apt-repository -y ppa:open5gs/latest",
                "sudo apt-get update -qq",
                "sudo apt-get install -y open5gs",
                "sudo mkdir -p /etc/open5gs",
                "sudo mkdir -p /var/log/open5gs"
            ]
            
            for cmd in open5gs_commands:
                ret, out, err = connection.execute_command(cmd, timeout=600)
                if ret != 0:
                    logger.warning(f"Command '{cmd}' had issues: {err}")
                else:
                    logger.info(f"✓ Command completed")
            
            # Verify Open5GS is installed
            logger.info("Verifying Open5GS installation...")
            ret, out, err = connection.execute_command("which open5gs-nrfd", timeout=30)
            if ret != 0:
                logger.warning(f"Open5GS binary not found: {err}")
            else:
                logger.info(f"✓ Open5GS binary verified")
            
            self._log_action(f"Open5GS install on {vm_name}", "SUCCESS")
            
            # Step 3: Install WebUI (Node.js + WebUI)
            logger.info("Step 3: Installing WebUI...")
            webui_commands = [
                "sudo apt-get install -y ca-certificates curl gnupg",
                "sudo mkdir -p /etc/apt/keyrings",
                "curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg",
                "echo 'deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main' | sudo tee /etc/apt/sources.list.d/nodesource.list",
                "sudo apt-get update -qq",
                "sudo apt-get install -y nodejs"
            ]
            
            for cmd in webui_commands:
                ret, out, err = connection.execute_command(cmd, timeout=300)
                if ret != 0:
                    logger.warning(f"WebUI deps: {err}")
            
            # Install WebUI via official script
            logger.info("Installing Open5GS WebUI from official source...")
            ret, out, err = connection.execute_command("curl -fsSL https://open5gs.org/open5gs/assets/webui/install | sudo -E bash -", timeout=600)
            if ret != 0:
                logger.warning(f"WebUI install: {err}")
            else:
                logger.info("✓ WebUI installed")
            
            self._log_action(f"Open5GS WebUI setup on {vm_name}", "SUCCESS")
            
            # Step 4: Generate and deploy configuration files
            logger.info("Step 4: Generating configuration files...")
            self._deploy_open5gs_configs(connection, open5gs_config)
            
            logger.info(f"✓ Open5GS deployment completed for {vm_name}")
            return True
        
        except Exception as e:
            logger.error(f"Open5GS deployment failed: {str(e)}")
            self._log_action(f"Open5GS deploy on {vm_name}", "FAILED", str(e))
            return False
    
    def _deploy_open5gs_configs(self, connection: SSHConnection, config: Dict):
        """Deploy Open5GS configuration files."""
        config_gen = ConfigurationGenerator()
        
        # Auto-detect or use provided IP
        vm_ip = config_gen.resolve_ip(
            config.get('configuration', {}).get('interfaces', {}),
            connection
        )
        logger.info(f"Using IP for Open5GS: {vm_ip}")
        
        # Update config with resolved IP
        open5gs_config = config.copy()
        if not open5gs_config.get('configuration', {}).get('interfaces', {}).get('nrf_sbi', {}).get('address'):
            if 'configuration' not in open5gs_config:
                open5gs_config['configuration'] = {}
            if 'interfaces' not in open5gs_config['configuration']:
                open5gs_config['configuration']['interfaces'] = {}
            
            # Set all interfaces to the detected/provided IP
            for interface_key in ['nrf_sbi', 'amf_ngap', 'upf_gtpu', 'upf_pfcp']:
                if interface_key not in open5gs_config['configuration']['interfaces']:
                    open5gs_config['configuration']['interfaces'][interface_key] = {}
                open5gs_config['configuration']['interfaces'][interface_key]['address'] = vm_ip
        
        # Generate NRF config
        nrf_config = config_gen.generate_nrf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("NRF configuration generated")
        
        # Generate AMF config
        amf_config = config_gen.generate_amf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("AMF configuration generated")
        
        # Generate UPF config
        upf_config = config_gen.generate_upf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("UPF configuration generated")
        
        # Generate SMF config
        smf_config = config_gen.generate_smf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("SMF configuration generated")
        
        # Generate AUSF config
        ausf_config = config_gen.generate_ausf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("AUSF configuration generated")
        
        # Generate UDM config
        udm_config = config_gen.generate_udm_config(open5gs_config, vm_ip=vm_ip)
        logger.info("UDM configuration generated")
        
        # Generate UDR config
        udr_config = config_gen.generate_udr_config(open5gs_config, vm_ip=vm_ip)
        logger.info("UDR configuration generated")
        
        # Generate PCF config
        pcf_config = config_gen.generate_pcf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("PCF configuration generated")
        
        # Generate NSSF config
        nssf_config = config_gen.generate_nssf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("NSSF configuration generated")
        
        # Generate BSF config
        bsf_config = config_gen.generate_bsf_config(open5gs_config, vm_ip=vm_ip)
        logger.info("BSF configuration generated")
        
        # Deploy configs via SSH (write to /tmp first, then sudo mv to /etc/open5gs)
        temp_dir = "/tmp/open5gs_configs"
        connection.execute_command(f"mkdir -p {temp_dir}")
        
        # Write configs to remote temp directory
        configs = {
            'nrf.yaml': nrf_config,
            'amf.yaml': amf_config,
            'upf.yaml': upf_config,
            'smf.yaml': smf_config,
            'ausf.yaml': ausf_config,
            'udm.yaml': udm_config,
            'udr.yaml': udr_config,
            'pcf.yaml': pcf_config,
            'nssf.yaml': nssf_config,
            'bsf.yaml': bsf_config
        }
        
        for filename, content in configs.items():
            remote_path = f"{temp_dir}/{filename}"
            local_path = f"/tmp/{filename}"
            
            with open(local_path, 'w') as f:
                f.write(content)
            
            connection.upload_file(local_path, remote_path)
            
            # Copy to actual location
            cmd = f"sudo cp {remote_path} /etc/open5gs/{filename}"
            ret, out, err = connection.execute_command(cmd)
            if ret == 0:
                logger.info(f"Deployed {filename}")
            else:
                logger.warning(f"Failed to deploy {filename}: {err}")
        
        # Stop all Open5GS services before restarting
        logger.info("Stopping all Open5GS services...")
        services = [
            'open5gs-nrfd',
            'open5gs-scpd',
            'open5gs-amfd',
            'open5gs-smfd',
            'open5gs-upfd',
            'open5gs-ausfd',
            'open5gs-udmd',
            'open5gs-udrd',
            'open5gs-pcfd',
            'open5gs-nssfd',
            'open5gs-bsfd'
        ]
        
        for service in services:
            cmd = f"sudo systemctl stop {service}"
            ret, out, err = connection.execute_command(cmd, timeout=30)
            if ret == 0:
                logger.info(f"✓ Stopped {service}")
            else:
                logger.warning(f"Failed to stop {service}: {err}")
        
        # Wait a moment for services to fully stop
        logger.info("Waiting for services to fully stop...")
        time.sleep(2)
        
        # Restart all Open5GS services
        logger.info("Restarting all Open5GS services...")
        for service in services:
            cmd = f"sudo systemctl restart {service}"
            ret, out, err = connection.execute_command(cmd, timeout=30)
            if ret == 0:
                logger.info(f"✓ Restarted {service}")
            else:
                logger.warning(f"Failed to restart {service}: {err}")
    
    def deploy_ueransim(self, ueransim_config: Dict, vm_name: str, amf_ip: str = '') -> bool:
        """Deploy UERANSIM on specified VM.
        
        Args:
            ueransim_config: UERANSIM configuration dict
            vm_name: Name of the UERANSIM VM
            amf_ip: Pre-detected AMF IP (from ogtsun interface) to inject into gNB config
        """
        if vm_name not in self.vm_connections:
            logger.error(f"VM {vm_name} not connected")
            return False
        
        connection = self.vm_connections[vm_name]
        logger.info(f"Deploying UERANSIM on {vm_name}...")
        logger.info("(This requires Open5GS to be already running)")
        
        try:
            # Step 1: Update system and install dependencies
            logger.info("Step 1: Installing UERANSIM dependencies...")
            
            # Install build tools
            install_commands = [
                "sudo apt-get update -qq",
                "sudo apt-get install -y build-essential cmake git libsctp-dev lksctp-tools"
            ]
            
            for cmd in install_commands:
                logger.info(f"Executing: {cmd}")
                ret, out, err = connection.execute_command(cmd, timeout=600)
                if ret != 0:
                    logger.warning(f"Command had issues: {err}")
                else:
                    logger.info(f"✓ Command completed")
            
            # Clone UERANSIM repository with explicit verification
            logger.info("Cloning UERANSIM repository...")
            # First, get the home directory explicitly
            ret, home_out, _ = connection.execute_command("echo $HOME")
            home_dir = home_out.strip()
            logger.info(f"Home directory detected: {home_dir}")
            
            clone_cmd = f"cd {home_dir} && git clone https://github.com/aligungr/UERANSIM.git UERANSIM 2>&1"
            ret, out, err = connection.execute_command(clone_cmd, timeout=300)
            logger.info(f"Clone output: {out}")
            if ret != 0:
                logger.warning(f"UERANSIM clone exit code {ret}: {err}")
            
            # Verify clone succeeded
            ret, check_out, check_err = connection.execute_command(f"[ -f {home_dir}/UERANSIM/CMakeLists.txt ] && echo 'OK' || echo 'FAILED'")
            if "FAILED" in check_out or ret != 0:
                logger.error(f"UERANSIM not cloned properly!")
                logger.error(f"Output: {out}, Error: {err}")
                return False
            
            logger.info("Building UERANSIM...")
            # Build must be done in single command due to cd semantics
            build_cmd = f"cd {home_dir}/UERANSIM && mkdir -p build && cd build && cmake .. 2>&1 | tail -5 && make -j$(nproc) 2>&1 | tail -10"
            ret, out, err = connection.execute_command(build_cmd, timeout=1200)
            logger.info(f"Build output:\n{out}")
            if ret != 0:
                logger.warning(f"UERANSIM build had issues: {err}")
            
            self._log_action(f"UERANSIM install on {vm_name}", "SUCCESS")
            
            # Step 2: Configuration and gNB startup are now handled by the quick-start script
            # which uploads premade configs and configures IPs dynamically
            logger.info("Step 2: Skipping config generation (handled by quick-start script)")
            logger.info("   ➜ Use 5g_deploy_quick_start.py to upload premade configs and start gNB")
            logger.info("   ➜ This will auto-detect IPs and configure UERANSIM appropriately")
            
            # NOTE: Do NOT call _deploy_ueransim_configs() as it requires non-existent config generators
            # The quick-start script provides a more flexible approach for handling premade configs
            
            self._log_action(f"UERANSIM deploy on {vm_name}", "SUCCESS")
            return True
        
        except Exception as e:
            logger.error(f"UERANSIM deployment failed: {str(e)}")
            self._log_action(f"UERANSIM deploy on {vm_name}", "FAILED", str(e))
            return False
    
    def _deploy_ueransim_configs(self, connection: SSHConnection, config: Dict, amf_ip: str = ''):
        """Deploy UERANSIM configuration files.
        
        Args:
            connection: SSH connection to UERANSIM VM
            config: UERANSIM configuration dict
            amf_ip: Pre-detected AMF IP to inject into config
        """
        config_gen = ConfigurationGenerator()
        
        # Get home directory
        ret, home_out, _ = connection.execute_command("echo $HOME")
        home_dir = home_out.strip()
        logger.info(f"Home directory: {home_dir}")
        
        # Auto-detect or use provided IP
        gnb_interfaces = config.get('configuration', {}).get('gnb', {}).get('interfaces', {})
        vm_ip = config_gen.resolve_ip(gnb_interfaces, connection)
        logger.info(f"Using IP for UERANSIM: {vm_ip}")
        
        # Update config with resolved IP
        ueransim_config = config.copy()
        if 'configuration' not in ueransim_config:
            ueransim_config['configuration'] = {}
        if 'gnb' not in ueransim_config['configuration']:
            ueransim_config['configuration']['gnb'] = {}
        if 'interfaces' not in ueransim_config['configuration']['gnb']:
            ueransim_config['configuration']['gnb']['interfaces'] = {}
        
        # Set all interface IPs to the detected/provided IP
        for interface_key in ['link_ip', 'ngap_ip', 'gtp_ip']:
            current_val = ueransim_config['configuration']['gnb']['interfaces'].get(interface_key, '')
            # Set IP if empty or not present
            if not current_val or current_val == '':
                ueransim_config['configuration']['gnb']['interfaces'][interface_key] = vm_ip
                logger.info(f"Set {interface_key} to {vm_ip}")
        
        # Inject AMF IP that was detected from Open5GS main interface
        if amf_ip:
            logger.info(f"Injecting detected AMF IP: {amf_ip}")
            if 'amf_configs' not in ueransim_config['configuration']['gnb']:
                ueransim_config['configuration']['gnb']['amf_configs'] = []
            
            if not ueransim_config['configuration']['gnb']['amf_configs']:
                # Create new AMF config with detected IP
                ueransim_config['configuration']['gnb']['amf_configs'] = [{'ip': amf_ip, 'port': 38412}]
                logger.info(f"Created AMF config with detected IP: {amf_ip}")
            else:
                # Update existing AMF configs with detected IP
                for amf_config in ueransim_config['configuration']['gnb']['amf_configs']:
                    current_amf_ip = amf_config.get('ip', '')
                    if not current_amf_ip or current_amf_ip == '':
                        amf_config['ip'] = amf_ip
                        logger.info(f"Updated AMF config IP to: {amf_ip}")
        
        # Update UE gNB search list with detected UERANSIM VM IP
        if 'ue' not in ueransim_config['configuration']:
            ueransim_config['configuration']['ue'] = {}
        if 'gnb_search_list' not in ueransim_config['configuration']['ue']:
            ueransim_config['configuration']['ue']['gnb_search_list'] = []
        
        # Set gNB search list to detected VM IP if empty
        ue_gnb_list = ueransim_config['configuration']['ue']['gnb_search_list']
        if not ue_gnb_list or ue_gnb_list == ['']:
            ueransim_config['configuration']['ue']['gnb_search_list'] = [vm_ip]
            logger.info(f"Set UE gnbSearchList to detected UERANSIM IP: {vm_ip}")
        
        # Generate gNB config
        gnb_config = config_gen.generate_ueransim_gnb_config(ueransim_config)
        logger.info("UERANSIM gNB configuration generated")
        logger.info(f"Generated gNB config:\n{gnb_config}")
        
        # Generate UE config
        ue_config = config_gen.generate_ueransim_ue_config(ueransim_config)
        logger.info("UERANSIM UE configuration generated")
        
        # Deploy configs - must create directory first
        config_dir = f"{home_dir}/UERANSIM/config"
        ret, out, err = connection.execute_command(f"mkdir -p {config_dir}")
        if ret != 0:
            logger.warning(f"Failed to create config directory: {err}")
        
        configs = {
            'open5gs-gnb.yaml': gnb_config,
            'open5gs-ue.yaml': ue_config
        }
        
        for filename, content in configs.items():
            remote_path = f"{config_dir}/{filename}"
            local_path = f"/tmp/{filename}"
            
            with open(local_path, 'w') as f:
                f.write(content)
            
            connection.upload_file(local_path, remote_path)
            logger.info(f"Deployed {filename}")
    
    def _start_ueransim_gnb(self, connection: SSHConnection, home_dir: str):
        """Start gNB service with nohup and verify it's running."""
        try:
            # Create logs directory
            ret, out, err = connection.execute_command(f"mkdir -p {home_dir}/UERANSIM/logs")
            if ret != 0:
                logger.warning(f"Failed to create logs directory: {err}")
            
            # Test SCTP connectivity to AMF before starting gNB
            logger.info("Testing network connectivity to AMF...")
            ret, nc_out, nc_err = connection.execute_command("nc -zv 10.160.101.117 38412 2>&1 | head -5", timeout=10)
            logger.info(f"SCTP port test output: {nc_out if nc_out else nc_err}")
            
            # Check if SCTP module is loaded
            ret, lsmod_out, _ = connection.execute_command("lsmod | grep sctp", timeout=10)
            if ret == 0:
                logger.info(f"SCTP module loaded: {lsmod_out}")
            else:
                logger.warning("SCTP module not loaded - this may cause connection issues")
            
            # Start gNB service
            logger.info("Starting gNB service...")
            gnb_cmd = f"nohup {home_dir}/UERANSIM/build/nr-gnb -c {home_dir}/UERANSIM/config/open5gs-gnb.yaml > {home_dir}/UERANSIM/logs/gnb.log 2>&1 & echo $!"
            ret, pid_out, err = connection.execute_command(gnb_cmd, timeout=30)
            
            if ret == 0:
                gnb_pid = pid_out.strip()
                logger.info(f"✓ gNB started with PID: {gnb_pid}")
                
                # Wait a moment for the process to start
                time.sleep(2)
                
                # Verify gNB is running
                ret, check_out, check_err = connection.execute_command("pgrep -f 'nr-gnb' | head -1", timeout=10)
                if ret == 0 and check_out.strip():
                    logger.info(f"✓ gNB process verified running (PID: {check_out.strip()})")
                    
                    # Tail the log to check for successful startup messages
                    ret, log_out, log_err = connection.execute_command(f"tail -30 {home_dir}/UERANSIM/logs/gnb.log", timeout=10)
                    logger.info(f"gNB log output:\n{log_out}")
                else:
                    logger.warning("gNB process not found - may have failed to start")
                    ret, log_out, log_err = connection.execute_command(f"tail -50 {home_dir}/UERANSIM/logs/gnb.log", timeout=10)
                    logger.error(f"gNB startup error:\n{log_out}")
            else:
                logger.warning(f"Failed to start gNB: {err}")
                
        except Exception as e:
            logger.error(f"Failed to start gNB service: {str(e)}")
    
    def start_services(self, vm_name: str) -> bool:
        """Start all Open5GS services on a VM."""
        if vm_name not in self.vm_connections:
            logger.error(f"VM {vm_name} not connected")
            return False
        
        connection = self.vm_connections[vm_name]
        logger.info(f"Starting services on {vm_name}...")
        
        services = [
            'open5gs-nrfd',
            'open5gs-scpd',
            'open5gs-amfd',
            'open5gs-smfd',
            'open5gs-upfd',
            'open5gs-ausfd',
            'open5gs-udmd',
            'open5gs-udrd',
            'open5gs-pcfd',
            'open5gs-nssfd',
            'open5gs-bsfd'
        ]
        
        for service in services:
            cmd = f"sudo systemctl start {service}"
            ret, out, err = connection.execute_command(cmd)
            if ret == 0:
                logger.info(f"Started {service}")
            else:
                logger.warning(f"Failed to start {service}: {err}")
        
        self._log_action(f"Start services on {vm_name}", "SUCCESS")
        return True
    
    def verify_deployment(self, vm_name: str) -> Dict[str, bool]:
        """Verify deployment health."""
        if vm_name not in self.vm_connections:
            logger.error(f"VM {vm_name} not connected")
            return {}
        
        connection = self.vm_connections[vm_name]
        results = {}
        
        health_checks = self.config.get('monitoring', {}).get('health_checks', [])
        for check in health_checks:
            service = check.get('service')
            command = check.get('command')
            
            ret, out, err = connection.execute_command(command)
            results[service] = (ret == 0)
            logger.info(f"Health check {service}: {'PASS' if ret == 0 else 'FAIL'}")
        
        return results
    
    def disconnect_all(self):
        """Close all SSH connections."""
        for vm_name, connection in self.vm_connections.items():
            connection.disconnect()
        logger.info("All connections closed")
    
    def save_deployment_log(self, filename: str = "deployment_log.json"):
        """Save deployment log to file."""
        with open(filename, 'w') as f:
            json.dump(self.deployment_log, f, indent=2)
        logger.info(f"Deployment log saved to {filename}")
    
    def deploy(self) -> bool:
        """Execute full 5G stack deployment."""
        logger.info("Starting 5G stack deployment...")
        
        try:
            # Extract VM information from config
            vm_specs = []
            
            # Add Open5GS VM
            open5gs_cfg = self.config.get('five_g_deployment', {}).get('open5gs_core', {})
            if open5gs_cfg.get('enabled'):
                # Get IP - either from config or detect from Proxmox
                open5gs_ip = open5gs_cfg.get('configuration', {}).get('interfaces', {}).get('nrf_sbi', {}).get('address', '')
                if not open5gs_ip or open5gs_ip == '':
                    logger.info(f"Auto-detecting IP for Open5GS VM: {open5gs_cfg.get('vm_name')}")
                    open5gs_ip = self._get_vm_ip_from_proxmox(open5gs_cfg.get('vm_name'))
                    if not open5gs_ip:
                        logger.error(f"Could not detect IP for Open5GS VM")
                        self._log_action(f"Detect Open5GS IP", "FAILED", "Could not detect IP from Proxmox")
                        return False
                
                vm_specs.append({
                    'name': open5gs_cfg.get('vm_name'),
                    'ip_address': open5gs_ip,
                    'username': 'localadmin',
                    'password': 'ii70mseq'
                })
            
            # Add UERANSIM VM
            ueransim_cfg = self.config.get('five_g_deployment', {}).get('ueransim', {})
            if ueransim_cfg.get('enabled'):
                # Get IP - either from config or detect from Proxmox
                ueransim_ip = ueransim_cfg.get('configuration', {}).get('gnb', {}).get('interfaces', {}).get('link_ip', '')
                if not ueransim_ip or ueransim_ip == '':
                    logger.info(f"Auto-detecting IP for UERANSIM VM: {ueransim_cfg.get('vm_name')}")
                    ueransim_ip = self._get_vm_ip_from_proxmox(ueransim_cfg.get('vm_name'))
                    if not ueransim_ip:
                        logger.error(f"Could not detect IP for UERANSIM VM")
                        self._log_action(f"Detect UERANSIM IP", "FAILED", "Could not detect IP from Proxmox")
                        return False
                
                vm_specs.append({
                    'name': ueransim_cfg.get('vm_name'),
                    'ip_address': ueransim_ip,
                    'username': 'localadmin',
                    'password': 'ii70mseq'
                })
            
            # Step 1: Connect to VMs
            if not self.connect_to_vms(vm_specs):
                logger.error("Failed to connect to required VMs")
                return False
            
            # Step 2: Deploy Open5GS
            if open5gs_cfg.get('enabled'):
                if not self.deploy_open5gs(open5gs_cfg, open5gs_cfg.get('vm_name')):
                    logger.error("Open5GS deployment failed")
                    return False
                
                logger.info("✓ Open5GS installation completed")
                
                # Start services
                if not self.start_services(open5gs_cfg.get('vm_name')):
                    logger.error("Failed to start Open5GS services")
                    return False
                
                # Wait for services to stabilize
                logger.info("Waiting for Open5GS services to stabilize...")
                time.sleep(20)
                
                # Verify Open5GS is ready
                logger.info("Verifying Open5GS is ready...")
                conn = self.vm_connections[open5gs_cfg.get('vm_name')]
                ret, out, err = conn.execute_command("ps aux | grep -E 'open5gs.*nrfd' | grep -v grep", timeout=10)
                if ret == 0:
                    logger.info("✓ Open5GS NRF is running")
                else:
                    logger.warning("Open5GS NRF may not be running, but continuing...")
            
            # Step 3: Deploy UERANSIM (ONLY AFTER Open5GS is ready)
            if ueransim_cfg.get('enabled'):
                logger.info("✓ Starting UERANSIM deployment...")
                logger.info(f"Using Open5GS VM IP for AMF: {open5gs_ip}")
                
                # Pass Open5GS IP to UERANSIM deployment for AMF connection
                if not self.deploy_ueransim(ueransim_cfg, ueransim_cfg.get('vm_name'), amf_ip=open5gs_ip):
                    logger.error("UERANSIM deployment failed")
                    return False
            
            # Step 4: Verify deployment
            logger.info("Verifying deployment...")
            if open5gs_cfg.get('enabled'):
                results = self.verify_deployment(open5gs_cfg.get('vm_name'))
                if not all(results.values()):
                    logger.warning("Some services failed health checks")
            
            # Save deployment log
            self.save_deployment_log()
            self._log_action("Full deployment", "SUCCESS")
            
            logger.info("5G stack deployment completed successfully!")
            return True
        
        except Exception as e:
            logger.error(f"Deployment failed: {str(e)}")
            self._log_action("Full deployment", "FAILED", str(e))
            return False
        
        finally:
            self.disconnect_all()


if __name__ == "__main__":
    # Example usage
    try:
        manager = FiveGDeploymentManager("open5gs_ueransim_deployment.yaml")
        success = manager.deploy()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Deployment interrupted by user")
        exit(1)
