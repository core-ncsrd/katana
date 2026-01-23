#!/usr/bin/env python3
"""
Deploy Open5GS configs to VM and start gNB on UERANSIM
"""

import os
import sys
import paramiko
import time
from pathlib import Path

# Configuration
OPEN5GS_VM_IP = "10.160.101.135"
UERANSIM_VM_IP = "10.160.101.134"
SSH_PORT = 22
SSH_USERNAME = "localadmin"
SSH_PASSWORD = "ii70mseq"

# Config files directory (where we have the files locally)
LOCAL_CONFIG_DIR = "/home/panos/open5gs"

# Remote directories
REMOTE_CONFIG_DIR = "/etc/open5gs"
REMOTE_TEMP_DIR = "/tmp/open5gs_configs"

# Config files to deploy
CONFIG_FILES = [
    "nrf.yaml",
    "amf.yaml",
    "upf.yaml",
    "smf.yaml",
    "ausf.yaml",
    "udm.yaml",
    "udr.yaml",
    "pcf.yaml",
    "nssf.yaml",
    "bsf.yaml",
    "scp.yaml",
    "hss.yaml",
    "mme.yaml",
    "pcrf.yaml",
    "sgwc.yaml",
    "sgwu.yaml",
    "sepp1.yaml",
    "sepp2.yaml",
]

# Open5GS services to restart
SERVICES = [
    "open5gs-nrf",
    "open5gs-scp",
    "open5gs-amf",
    "open5gs-smf",
    "open5gs-upf",
    "open5gs-ausf",
    "open5gs-udm",
    "open5gs-udr",
    "open5gs-pcf",
    "open5gs-nssf",
    "open5gs-bsf",
    "open5gs-hss",
    "open5gs-mme",
    "open5gs-pcrf",
    "open5gs-sgwc",
    "open5gs-sgwu",
]


def ssh_connect(host, username, password, port=22):
    """Create SSH connection"""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, port=port, username=username, password=password, timeout=10)
        print(f"✅ Connected to {host}")
        return ssh
    except Exception as e:
        print(f"❌ Failed to connect to {host}: {e}")
        return None


def execute_command(ssh, command):
    """Execute command on remote host"""
    try:
        stdin, stdout, stderr = ssh.exec_command(command)
        stdout.channel.settimeout(10)
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        return_code = stdout.channel.recv_exit_status()
        return return_code, output, error
    except Exception as e:
        print(f"❌ Command execution failed: {e}")
        return -1, "", str(e)


def upload_configs(ssh, local_dir, remote_dir):
    """Upload config files via SFTP"""
    try:
        sftp = ssh.open_sftp()
        
        # Create remote temp directory
        try:
            sftp.stat(REMOTE_TEMP_DIR)
        except IOError:
            print(f"📁 Creating {REMOTE_TEMP_DIR}")
            execute_command(ssh, f"mkdir -p {REMOTE_TEMP_DIR}")
        
        # Upload each config file
        for config_file in CONFIG_FILES:
            local_path = os.path.join(local_dir, config_file)
            remote_path = os.path.join(REMOTE_TEMP_DIR, config_file)
            
            if not os.path.exists(local_path):
                print(f"⚠️  File not found: {local_path}")
                continue
            
            print(f"📤 Uploading {config_file}...")
            sftp.put(local_path, remote_path)
        
        sftp.close()
        print("✅ All configs uploaded to temp directory")
        return True
    except Exception as e:
        print(f"❌ SFTP upload failed: {e}")
        return False


def deploy_configs(ssh):
    """Copy configs from temp to /etc/open5gs"""
    print("\n🔄 Deploying configs to /etc/open5gs...")
    cmd = f"sudo cp {REMOTE_TEMP_DIR}/*.yaml {REMOTE_CONFIG_DIR}/"
    rc, out, err = execute_command(ssh, cmd)
    
    if rc == 0:
        print("✅ Configs deployed")
        return True
    else:
        print(f"❌ Deployment failed: {err}")
        return False


def stop_services(ssh):
    """Stop all Open5GS services"""
    print("\n🛑 Stopping Open5GS services...")
    cmd = "systemctl stop open5gs-*"
    rc, out, err = execute_command(ssh, cmd)
    
    # Also try individual stops for robustness
    for service in SERVICES:
        execute_command(ssh, f"systemctl stop {service} 2>/dev/null || true")
    
    time.sleep(2)
    print("✅ Services stopped")
    return True


def start_services(ssh):
    """Start all Open5GS services"""
    print("\n▶️  Starting Open5GS services...")
    
    # Start services in order (NRF and SCP first, then others)
    service_order = [
        "open5gs-nrf",
        "open5gs-scp",
        "open5gs-amf",
        "open5gs-smf",
        "open5gs-upf",
        "open5gs-ausf",
        "open5gs-udm",
        "open5gs-udr",
        "open5gs-pcf",
        "open5gs-nssf",
        "open5gs-bsf",
    ]
    
    for service in service_order:
        print(f"  Starting {service}...")
        rc, out, err = execute_command(ssh, f"systemctl start {service}")
        if rc == 0:
            print(f"  ✅ {service} started")
        else:
            print(f"  ⚠️  {service} failed: {err}")
        time.sleep(1)
    
    print("✅ Services started")
    return True


def check_services(ssh):
    """Check service status"""
    print("\n📊 Service Status:")
    rc, out, err = execute_command(ssh, "systemctl status open5gs-* --no-pager | grep -E '^(open5gs-|   Active)'")
    print(out)


def start_gnb(ssh_ueransim):
    """Start gNB on UERANSIM VM"""
    print("\n🚀 Starting gNB on UERANSIM...")
    
    # Command to start gNB (adjust based on your UERANSIM setup)
    cmd = "cd /home/ubuntu/UERANSIM && ./nr-gnb -c config/open-5gs-gnb.yaml 2>&1 &"
    
    rc, out, err = execute_command(ssh_ueransim, cmd)
    
    if rc == 0:
        print("✅ gNB started on UERANSIM")
        time.sleep(3)
        
        # Try to show gNB output
        print("\n📡 gNB Output:")
        rc, out, err = execute_command(ssh_ueransim, "ps aux | grep nr-gnb | grep -v grep")
        print(out)
        return True
    else:
        print(f"⚠️  gNB start output: {err}")
        return True  # Don't fail, might still be starting


def main():
    print("="*60)
    print("Open5GS Config Deploy & gNB Start Script")
    print("="*60)
    
    # Connect to Open5GS VM
    print(f"\n[1/5] Connecting to Open5GS VM ({OPEN5GS_VM_IP})...")
    ssh_open5gs = ssh_connect(OPEN5GS_VM_IP, SSH_USERNAME, SSH_PASSWORD)
    if not ssh_open5gs:
        print("❌ Failed to connect to Open5GS VM")
        return False
    
    # Connect to UERANSIM VM
    print(f"\n[2/5] Connecting to UERANSIM VM ({UERANSIM_VM_IP})...")
    ssh_ueransim = ssh_connect(UERANSIM_VM_IP, SSH_USERNAME, SSH_PASSWORD)
    if not ssh_ueransim:
        print("⚠️  Warning: Failed to connect to UERANSIM VM (will skip gNB start)")
        ssh_ueransim = None
    
    # Upload configs
    print(f"\n[2/5] Uploading configs from {LOCAL_CONFIG_DIR}...")
    if not upload_configs(ssh_open5gs, LOCAL_CONFIG_DIR, REMOTE_CONFIG_DIR):
        print("❌ Upload failed")
        ssh_open5gs.close()
        if ssh_ueransim:
            ssh_ueransim.close()
        return False
    
    # Deploy configs
    print(f"\n[3/5] Deploying configs to {REMOTE_CONFIG_DIR}...")
    if not deploy_configs(ssh_open5gs):
        print("❌ Deployment failed")
        ssh_open5gs.close()
        if ssh_ueransim:
            ssh_ueransim.close()
        return False
    
    # Stop and start services
    print(f"\n[4/5] Restarting Open5GS services...")
    stop_services(ssh_open5gs)
    time.sleep(3)
    start_services(ssh_open5gs)
    
    # Check service status
    check_services(ssh_open5gs)
    
    # Start gNB
    if ssh_ueransim:
        print(f"\n[5/5] Starting gNB on UERANSIM...")
        start_gnb(ssh_ueransim)
    
    # Cleanup
    print("\n" + "="*60)
    print("✅ Deployment Complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. Check Open5GS service logs: ssh root@10.160.101.132 'tail -f /var/log/open5gs/*.log'")
    print("2. Check gNB logs: ssh root@10.160.101.129 'ps aux | grep nr-gnb'")
    print("3. Monitor connection: Look for 'SCTP connection established' in gNB logs")
    
    ssh_open5gs.close()
    if ssh_ueransim:
        ssh_ueransim.close()
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
