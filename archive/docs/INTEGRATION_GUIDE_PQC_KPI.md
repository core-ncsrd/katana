# PQC KPI Module Integration Guide

## Overview

The `katana-pqc-kpi` module has been successfully integrated into the Katana Slice Manager project. This guide explains what was added, how it works, and how to use it.

## What Was Added

### New Directory Structure
```
katana-pqc-kpi/
├── .dockerignore               # Docker build ignore file
├── Dockerfile                  # Container image definition
├── README.md                   # Module documentation
├── requirements.txt            # Python dependencies
├── sample_report_generator.py  # Test/demo script
├── katana/
│   ├── __init__.py            # Package initialization
│   └── pqc_server.py          # Main Flask application
└── templates/
    └── index.html              # Web dashboard
```

## How It Works

### Architecture

The PQC KPI module operates as a standalone microservice with two main components:

1. **UDP Listener** (Background Thread)
   - Listens on port 5005 for incoming JSON reports
   - Stores up to 50 most recent events in memory
   - Adds metadata (reporter IP) to each event
   - Logs all activities

2. **Flask Web Server** (HTTP)
   - Serves the dashboard on port 8080
   - Provides RESTful API endpoints
   - Serves static HTML/CSS/JavaScript
   - Thread-safe event access

### Data Flow

```
PQC Analyzer Script
        ↓
   UDP Report (JSON)
        ↓
UDP Listener (port 5005)
        ↓
In-Memory Event Queue
        ↓
Flask API Endpoints
        ↓
Web Dashboard (Browser)
```

## Integration with Katana

### Docker Compose

The module has been added to `docker-compose.yaml`:

```yaml
katana-pqc-kpi:
  image: "${DOCKER_REG}${DOCKER_REPO}katana-pqc-kpi:${DOCKER_TAG}"
  build:
    context: .
    dockerfile: katana-pqc-kpi/Dockerfile
  container_name: katana-pqc-kpi
  ports:
    - "8080:8080"
    - "5005:5005/udp"
  environment:
    PYTHONUNBUFFERED: "1"
  restart: unless-stopped
```

### Port Mappings

| Port | Protocol | Purpose |
|------|----------|---------|
| 8080 | TCP | Web Dashboard & API |
| 5005 | UDP | PQC Analyzer Report Ingestion |

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Build all Katana services including PQC KPI
docker-compose build

# Start the services
docker-compose up -d katana-pqc-kpi

# Access the dashboard
open http://localhost:8080
```

### Option 2: Local Development

```bash
# Navigate to the module
cd katana-pqc-kpi

# Install dependencies
pip install -r requirements.txt

# Run the server
python -m katana.pqc_server

# In another terminal, send test reports
python sample_report_generator.py

# Access the dashboard
open http://localhost:8080
```

## API Reference

### Dashboard
- **URL**: `http://localhost:8080/`
- **Method**: GET
- **Returns**: Interactive HTML dashboard with real-time updates

### Get Events
- **URL**: `/api/events`
- **Method**: GET
- **Returns**: JSON array of all captured events

Example response:
```json
[
  {
    "burst_summary": {
      "exchange_type": "KEM",
      "algorithm": "Kyber-768",
      "success": true
    },
    "metrics": {
      "key_generation_time_ms": 2.34,
      "encryption_time_ms": 0.56,
      "decryption_time_ms": 0.61,
      "key_size_bytes": 1152,
      "ciphertext_size_bytes": 1088
    },
    "timestamp": "2024-01-12T10:30:45.123Z",
    "node_id": "analyzer-1",
    "batch_id": 5432,
    "_reporter_ip": "192.168.1.100"
  }
]
```

### Get Statistics
- **URL**: `/api/stats`
- **Method**: GET
- **Returns**: Aggregated statistics

Example response:
```json
{
  "total_events": 156,
  "exchange_types": {
    "KEM": 89,
    "Signature": 52,
    "Hybrid": 15
  },
  "reporter_ips": {
    "192.168.1.100": 78,
    "192.168.1.101": 45,
    "192.168.1.102": 33
  }
}
```

### Clear Events
- **URL**: `/api/clear`
- **Method**: GET
- **Returns**: Status message
- **Effect**: Clears all events from memory

## Sending Reports from Analyzer Scripts

### Python Example

```python
import json
import socket

def send_pqc_report(exchange_type, metrics, target_host="localhost"):
    """Send a PQC KPI report to the monitoring service."""
    report = {
        "burst_summary": {
            "exchange_type": exchange_type  # "KEM", "Signature", or "Hybrid"
        },
        "metrics": metrics,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(json.dumps(report).encode(), (target_host, 5005))
    sock.close()

# Example usage
metrics = {
    "algorithm": "Kyber-768",
    "key_generation_ms": 2.5,
    "encryption_ms": 0.8,
    "decryption_ms": 0.9
}
send_pqc_report("KEM", metrics)
```

### C/C++ Example

```c
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <time.h>

void send_pqc_report(const char *exchange_type) {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in addr;
    
    addr.sin_family = AF_INET;
    addr.sin_port = htons(5005);
    inet_aton("127.0.0.1", &addr.sin_addr);
    
    // Create JSON report
    char report[512];
    snprintf(report, sizeof(report),
        "{\"burst_summary\": {\"exchange_type\": \"%s\"}}",
        exchange_type);
    
    sendto(sock, report, strlen(report), 0,
           (struct sockaddr*)&addr, sizeof(addr));
    
    close(sock);
}
```

## Testing with Sample Generator

The module includes `sample_report_generator.py` for testing:

```bash
# Terminal 1: Start the server
python -m katana.pqc_server

# Terminal 2: Run the generator
python sample_report_generator.py

# Terminal 3: Access dashboard
curl http://localhost:8080/api/events
```

The generator creates realistic test reports with:
- Random exchange types (KEM, Signature, Hybrid)
- Random algorithms (Kyber, Dilithium variants)
- Simulated performance metrics
- 75% success rate for realism

## Monitoring and Debugging

### View Logs

Docker:
```bash
docker logs katana-pqc-kpi -f
```

Local:
```
Check stdout where you ran the server
```

### Common Issues

1. **"Connection refused" when accessing dashboard**
   - Ensure port 8080 is not blocked
   - Check if the service is running: `docker ps | grep pqc`

2. **"No events captured"**
   - Verify analyzer is sending to correct host/port
   - Check firewall allows UDP 5005
   - Run sample generator to test connectivity

3. **Events not visible**
   - Refresh the browser page (or wait 2 seconds for auto-refresh)
   - Check API endpoint directly: `curl http://localhost:8080/api/events`

## Metrics Captured

The module can capture and display:

- **Exchange Type**: KEM, Signature, Hybrid
- **Algorithm**: Specific PQC algorithm used
- **Performance Metrics**: Key generation, encryption, decryption times
- **Key Sizes**: Input key size, ciphertext size
- **Success/Failure Status**: Whether the operation succeeded
- **Timing Information**: Timestamps for all operations
- **Source Information**: Node ID, batch ID, reporter IP

## Future Enhancements

Potential improvements for future versions:

1. **Persistent Storage**
   - Add MongoDB/PostgreSQL backend
   - Query historical data

2. **Advanced Visualization**
   - Performance trending graphs
   - Algorithm comparison charts
   - Heat maps for multi-node deployments

3. **Alerting**
   - Threshold-based alerts
   - Failure rate monitoring
   - Performance degradation detection

4. **Integration with Katana Core**
   - Expose metrics via Prometheus format
   - Integrate with Grafana dashboards
   - Add slice-specific monitoring

5. **Security**
   - Authentication/Authorization
   - TLS for UDP (DTLS)
   - Rate limiting

## Files Reference

### pqc_server.py
Main application file containing:
- Flask application factory
- UDP listener thread
- API endpoint definitions
- Event processing logic

### index.html
Interactive web dashboard featuring:
- Real-time event display
- Statistics cards
- Control buttons
- Auto-refresh mechanism
- Responsive design

### sample_report_generator.py
Testing utility that:
- Generates random test reports
- Simulates multiple analyzers
- Sends reports via UDP
- Useful for testing and demos

### Dockerfile
Container image definition that:
- Uses Python 3.9 slim base
- Installs dependencies
- Exposes ports 8080 and 5005
- Sets up proper environment

## Dependencies

- Python 3.9+
- Flask 2.0.0+
- Standard library: socket, threading, json, collections, logging

## Notes

- Events are stored in memory only (cleared on restart)
- Maximum 50 events retained (configurable via MAX_HISTORY)
- UDP is connectionless (reports may be lost in extreme conditions)
- Dashboard auto-refreshes every 2 seconds
- All timestamps are in UTC/ISO format

## Support

For issues or questions:
1. Check the module README.md
2. Review logs for error messages
3. Test with sample_report_generator.py
4. Verify network connectivity and port availability

---

**Module Version**: 1.0.0
**Created**: January 2024
**Status**: Production Ready
