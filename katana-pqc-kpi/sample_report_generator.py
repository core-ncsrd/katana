#!/usr/bin/env python3
"""
Sample PQC KPI Report Generator for Testing
This script demonstrates how to send test reports to the PQC KPI monitoring service.
"""

import socket
import json
import time
import random
from datetime import datetime
import hashlib

# Configuration
TARGET_HOST = "localhost"
TARGET_PORT = 5005

EXCHANGE_TYPES = ["KEM", "Signature", "Hybrid"]
ALGORITHMS = [
    "Kyber-512", "Kyber-768", "Kyber-1024",
    "Dilithium-2", "Dilithium-3", "Dilithium-5",
    "FALCON-512", "FALCON-1024"
]

def generate_key_fragment(size_bytes):
    """Generate a hex fragment of a key."""
    fragment_size = min(32, size_bytes // 2)
    random_bytes = bytes([random.randint(0, 255) for _ in range(fragment_size)])
    return random_bytes.hex()[:64]  # Return hex string limited to 64 chars

def create_sample_report():
    """Create a sample PQC KPI report with detailed key and certificate info."""
    algorithm = random.choice(ALGORITHMS)
    exchange_type = "KEM" if "Kyber" in algorithm else ("Signature" if "Dilithium" in algorithm else "Hybrid")
    
    # Simulate realistic key sizes based on algorithm
    if "512" in algorithm:
        key_size = 800 + random.randint(-50, 50)
        cert_size = 1200 + random.randint(-100, 100)
    elif "768" in algorithm:
        key_size = 1184 + random.randint(-50, 50)
        cert_size = 1800 + random.randint(-100, 100)
    else:  # 1024
        key_size = 1568 + random.randint(-50, 50)
        cert_size = 2400 + random.randint(-100, 100)
    
    total_packet_size = key_size + cert_size + random.randint(100, 500)
    
    return {
        "burst_summary": {
            "exchange_type": exchange_type,
            "algorithm": algorithm,
            "success": random.choice([True, True, True, False])  # 75% success rate
        },
        "metrics": {
            "key_generation_time_ms": round(random.uniform(0.5, 50.0), 2),
            "encryption_time_ms": round(random.uniform(0.1, 20.0), 2),
            "decryption_time_ms": round(random.uniform(0.1, 20.0), 2),
            "key_size_bytes": key_size,
            "certificate_size_bytes": cert_size,
            "total_packet_size": total_packet_size,
            "key_fragment": generate_key_fragment(key_size),
            "certificate_fragment": generate_key_fragment(cert_size),
            "compression_ratio": round(random.uniform(0.85, 0.99), 3)
        },
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "node_id": f"analyzer-{random.randint(1, 3)}",
        "batch_id": random.randint(1000, 9999)
    }

def send_report(report, host=TARGET_HOST, port=TARGET_PORT):
    """Send a report to the PQC KPI service via UDP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        json_str = json.dumps(report)
        sock.sendto(json_str.encode('utf-8'), (host, port))
        sock.close()
        print(f"[+] Sent report: {report['burst_summary']['exchange_type']} - "
              f"{report['burst_summary']['algorithm']}")
    except Exception as e:
        print(f"[-] Error sending report: {e}")

def main():
    """Main test loop."""
    print(f"PQC KPI Report Generator")
    print(f"Target: {TARGET_HOST}:{TARGET_PORT}")
    print(f"Press Ctrl+C to stop\n")
    
    try:
        while True:
            # Generate and send a random report
            report = create_sample_report()
            send_report(report)
            
            # Wait before sending next report (0.5-2 seconds)
            time.sleep(random.uniform(0.5, 2.0))
    except KeyboardInterrupt:
        print("\n[*] Stopped by user")

if __name__ == "__main__":
    main()
