#!/bin/bash

# Apply minimal required fields to Open5GS configs
set -e

CONFIG_DIR="/etc/open5gs"

echo "[*] Fixing configuration files with required fields..."

# Fix AMF - add amf_name
echo "  [*] Fixing AMF..."
sudo sed -i '/^amf:/a\  amf_name: amf' $CONFIG_DIR/amf.yaml

# Fix SMF - add gtpu address and upf config
echo "  [*] Fixing SMF..."
if ! sudo grep -q "gtpu:" $CONFIG_DIR/smf.yaml; then
    sudo sed -i '/^smf:/a\  gtpu:\n    server:\n      - address: 127.0.0.4\n        port: 2152' $CONFIG_DIR/smf.yaml
fi

# Fix NSSF - add nsi config
echo "  [*] Fixing NSSF..."
if ! sudo grep -q "nsi:" $CONFIG_DIR/nssf.yaml; then
    sudo sed -i '/^nssf:/a\  nsi:\n    - plmn_id:\n        mcc: 999\n        mnc: "70"' $CONFIG_DIR/nssf.yaml
fi

echo "  [✓] Config fixes applied"

echo ""
echo "[*] Restarting services..."
sudo systemctl restart open5gs-amfd open5gs-smfd open5gs-nssfd
sleep 3

echo ""
echo "[*] Service status:"
for svc in amfd smfd nssfd; do
    status=$(sudo systemctl is-active open5gs-$svc 2>/dev/null || echo "failed")
    echo "  open5gs-$svc: $status"
done

echo ""
echo "[*] Checking NGAP port..."
if sudo netstat -tlnp 2>/dev/null | grep -q "38412"; then
    echo "  [✓] NGAP port 38412 is NOW LISTENING!"
    sudo netstat -tlnp 2>/dev/null | grep 38412 || true
else
    echo "  [!] Still not listening, checking AMF status:"
    sudo systemctl status open5gs-amfd | tail -10
fi
