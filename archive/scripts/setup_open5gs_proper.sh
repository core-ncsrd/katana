#!/bin/bash

# Proper Open5GS Configuration Fix for External VM Deployment
# This script sets up all Open5GS services with correct localhost bindings
# while keeping NGAP on the external IP for gNB connectivity

set -e

VM_IP="${1:-10.160.101.132}"
CONFIG_DIR="/etc/open5gs"

echo "========================================="
echo "Open5GS Proper Configuration Setup"
echo "========================================="
echo "VM IP: $VM_IP"
echo "Config Dir: $CONFIG_DIR"
echo ""

# Stop all services first
echo "[*] Stopping all Open5GS services..."
sudo systemctl stop open5gs-* 2>/dev/null || true
sleep 3

# Backup original configs
echo "[*] Backing up original configs..."
sudo cp -r $CONFIG_DIR $CONFIG_DIR.backup.$(date +%s) 2>/dev/null || true

# Reinstall to get clean configs
echo "[*] Reinstalling Open5GS to restore clean configs..."
sudo apt-get install --reinstall -o DPkg::Options::=--force-confmiss open5gs 2>&1 | grep -i "done\|complete" || true
sleep 2

echo ""
echo "[*] Configuring services..."

# 1. Configure NRF (Network Repository Function)
echo "  [*] NRF configuration..."
sudo tee $CONFIG_DIR/nrf.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/nrf.log

global:
  max:
    ue: 1024

nrf:
  serving:
    - plmn_id:
        mcc: 999
        mnc: 70
  sbi:
    server:
      - address: 127.0.0.10
        port: 7777
  logging:
    level: debug
EOF
echo "  [✓] NRF configured"

# 2. Configure SCP (Service Communication Proxy) 
echo "  [*] SCP configuration..."
sudo tee $CONFIG_DIR/scp.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/scp.log

global:
  max:
    peer: 64

scp:
  sbi:
    server:
      - address: 127.0.0.200
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
  logging:
    level: debug
EOF
echo "  [✓] SCP configured"

# 3. Configure AMF (Access and Mobility Management Function)
echo "  [*] AMF configuration..."
sudo tee $CONFIG_DIR/amf.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/amf.log

global:
  max:
    ue: 1024

amf:
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
      - address: 10.160.101.132
        port: 38412
  guami:
    - plmn_id:
        mcc: 999
        mnc: '70'
      amf_id:
        region: 2
        set: 1
  tai:
    - plmn_id:
        mcc: 999
        mnc: '70'
      tac: 1
  plmn_support:
    - plmn_id:
        mcc: 999
        mnc: '70'
      s_nssai:
        - sst: 1
  security:
    integrity_order: ["NIA2", "NIA1", "NIA0"]
    ciphering_order: ["NEA0", "NEA1", "NEA2"]
  network_name:
    full: "Open5GS"
  logging:
    level: debug
EOF
echo "  [✓] AMF configured"

# 4. Configure SMF (Session Management Function)
echo "  [*] SMF configuration..."
sudo tee $CONFIG_DIR/smf.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/smf.log

global:
  max:
    ue: 1024

smf:
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.4
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
        - address: 127.0.0.7
  gtpc:
    server:
      - address: 127.0.0.4
        port: 2123
  subnet:
    - addr: 10.45.0.1/16
    - addr: 2001:db8:cafe::1/48
  dns:
    - 8.8.8.8
    - 8.8.4.4
  mtu: 1400
  logging:
    level: debug
EOF
echo "  [✓] SMF configured"

# 5. Configure UPF (User Plane Function)
echo "  [*] UPF configuration..."
sudo tee $CONFIG_DIR/upf.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/upf.log

global:
  max:
    ue: 1024

upf:
  pfcp:
    server:
      - address: 127.0.0.7
        port: 8805
    client:
      smf:
        - address: 127.0.0.4
  gtpu:
    server:
      - address: 127.0.0.7
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
EOF
echo "  [✓] UPF configured"

# 6. Configure AUSF (Authentication Server Function)
echo "  [*] AUSF configuration..."
sudo tee $CONFIG_DIR/ausf.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/ausf.log

global:
  max:
    ue: 1024

ausf:
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.11
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
EOF
echo "  [✓] AUSF configured"

# 7. Configure UDM (Unified Data Management)
echo "  [*] UDM configuration..."
sudo tee $CONFIG_DIR/udm.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/udm.log

global:
  max:
    ue: 1024

udm:
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.12
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
EOF
echo "  [✓] UDM configured"

# 8. Configure UDR (Unified Data Repository)
echo "  [*] UDR configuration..."
sudo tee $CONFIG_DIR/udr.yaml > /dev/null << 'EOF'
db_uri: mongodb://localhost/open5gs
logger:
  file:
    path: /var/log/open5gs/udr.log

global:
  max:
    ue: 1024

udr:
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.20
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
EOF
echo "  [✓] UDR configured"

# 9. Configure PCF (Policy and Charging Function)
echo "  [*] PCF configuration..."
sudo tee $CONFIG_DIR/pcf.yaml > /dev/null << 'EOF'
db_uri: mongodb://localhost/open5gs
logger:
  file:
    path: /var/log/open5gs/pcf.log

global:
  max:
    ue: 1024

pcf:
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.13
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
EOF
echo "  [✓] PCF configured"

# 10. Configure NSSF (Network Slice Selection Function)
echo "  [*] NSSF configuration..."
sudo tee $CONFIG_DIR/nssf.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/nssf.log

global:
  max:
    ue: 1024

nssf:
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.14
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
EOF
echo "  [✓] NSSF configured"

# 11. Configure BSF (Binding Support Function)
echo "  [*] BSF configuration..."
sudo tee $CONFIG_DIR/bsf.yaml > /dev/null << 'EOF'
logger:
  file:
    path: /var/log/open5gs/bsf.log

global:
  max:
    ue: 1024

bsf:
  nrf:
    uri: http://127.0.0.10:7777
  sbi:
    server:
      - address: 127.0.0.15
        port: 7777
    client:
      nrf:
        - uri: http://127.0.0.10:7777
      scp:
        - uri: http://127.0.0.200:7777
  logging:
    level: debug
EOF
echo "  [✓] BSF configured"

echo ""
echo "[*] Starting Open5GS services in correct order..."

# Start NRF first
echo "  [*] Starting NRF..."
sudo systemctl start open5gs-nrfd
sleep 3

# Start SCP
echo "  [*] Starting SCP..."
sudo systemctl start open5gs-scpd
sleep 2

# Start other services
echo "  [*] Starting remaining services..."
sudo systemctl start open5gs-amfd open5gs-smfd open5gs-upfd \
    open5gs-ausfd open5gs-udmd open5gs-udrd open5gs-pcfd open5gs-nssfd open5gs-bsfd
sleep 3

echo ""
echo "[*] Verifying services..."
echo ""

for service in nrfd scpd amfd smfd upfd ausfd udmd udrd pcfd nssfd bsfd; do
    status=$(sudo systemctl is-active open5gs-$service 2>/dev/null || echo "failed")
    if [ "$status" = "active" ]; then
        echo "  [✓] open5gs-$service is running"
    else
        echo "  [✗] open5gs-$service is $status"
        echo "      Error logs:"
        sudo journalctl -u open5gs-$service -n 5 --no-pager | sed 's/^/        /'
    fi
done

echo ""
echo "[*] Checking critical ports..."
echo ""

if sudo netstat -tlnp 2>/dev/null | grep -q "38412"; then
    echo "  [✓] NGAP port 38412 is listening"
    sudo netstat -tlnp 2>/dev/null | grep 38412
else
    echo "  [✗] NGAP port 38412 is NOT listening"
fi

echo ""
echo "========================================="
echo "Configuration setup completed!"
echo "========================================="
