#!/bin/bash

# Fix Open5GS Configuration for External IP Connectivity
# This script properly updates all Open5GS service configs to use the external VM IP
# instead of localhost loopback addresses

set -e

VM_IP="${1:-10.160.101.132}"
CONFIG_DIR="/etc/open5gs"

echo "========================================="
echo "Open5GS Configuration Fix"
echo "========================================="
echo "VM IP: $VM_IP"
echo "Config Dir: $CONFIG_DIR"
echo ""

# Define the mapping of services to their localhost IPs
declare -A SERVICE_IPS
SERVICE_IPS["nrf.yaml"]=127.0.0.10
SERVICE_IPS["scp.yaml"]=127.0.0.200
SERVICE_IPS["amf.yaml"]=127.0.0.5
SERVICE_IPS["smf.yaml"]=127.0.0.4
SERVICE_IPS["upf.yaml"]=127.0.0.7
SERVICE_IPS["ausf.yaml"]=127.0.0.11
SERVICE_IPS["udm.yaml"]=127.0.0.12
SERVICE_IPS["pcf.yaml"]=127.0.0.13
SERVICE_IPS["nssf.yaml"]=127.0.0.14
SERVICE_IPS["bsf.yaml"]=127.0.0.15
SERVICE_IPS["udr.yaml"]=127.0.0.20

echo "[*] Fixing localhost references to use external IP..."
for config_file in "${!SERVICE_IPS[@]}"; do
    if [ -f "$CONFIG_DIR/$config_file" ]; then
        local_ip="${SERVICE_IPS[$config_file]}"
        
        # Replace specific localhost IP with VM IP (not the generic 127.0.0.x pattern)
        sudo sed -i "s/$local_ip/$VM_IP/g" "$CONFIG_DIR/$config_file"
        
        # Also replace generic NRF reference if present
        sudo sed -i "s|uri: http://127.0.0.10:7777|uri: http://$VM_IP:7777|g" "$CONFIG_DIR/$config_file"
        sudo sed -i "s|uri: http://127.0.0.200:7777|uri: http://$VM_IP:7777|g" "$CONFIG_DIR/$config_file"
        
        echo "  [✓] Fixed $config_file"
    else
        echo "  [!] Skipping $config_file (not found)"
    fi
done

echo ""
echo "[*] Restarting Open5GS services..."

# Stop all services first
echo "  [*] Stopping services..."
sudo systemctl stop open5gs-nrfd open5gs-scpd open5gs-amfd open5gs-smfd \
    open5gs-ausfd open5gs-udmd open5gs-pcfd open5gs-nssfd open5gs-bsfd 2>/dev/null || true
sleep 2

# Start services in the correct order (NRF first, then others)
echo "  [*] Starting NRF..."
sudo systemctl start open5gs-nrfd
sleep 3

echo "  [*] Starting SCP..."
sudo systemctl start open5gs-scpd
sleep 2

echo "  [*] Starting other services..."
sudo systemctl start open5gs-amfd open5gs-smfd open5gs-ausfd open5gs-udmd \
    open5gs-pcfd open5gs-nssfd open5gs-bsfd
sleep 3

echo ""
echo "[*] Verifying services..."
echo ""

for service in nrfd scpd amfd smfd ausfd udmd pcfd nssfd bsfd; do
    status=$(sudo systemctl is-active open5gs-$service 2>/dev/null || echo "inactive")
    if [ "$status" = "active" ]; then
        echo "  [✓] open5gs-$service is running"
    else
        echo "  [✗] open5gs-$service is $status"
    fi
done

echo ""
echo "[*] Checking NGAP port 38412..."
if sudo netstat -tlnp 2>/dev/null | grep -q "38412"; then
    echo "  [✓] NGAP port 38412 is listening"
    sudo netstat -tlnp 2>/dev/null | grep 38412
else
    echo "  [!] NGAP port 38412 is NOT listening"
    echo "  [!] Checking AMF status..."
    sudo systemctl status open5gs-amfd | tail -5
fi

echo ""
echo "========================================="
echo "Configuration fix completed!"
echo "========================================="
