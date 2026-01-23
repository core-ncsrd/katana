# Katana PQC KPI Monitoring Module

Post-Quantum Cryptography (PQC) Key Performance Indicators Monitoring Service

## Overview

The `katana-pqc-kpi` module is a Flask-based microservice that provides real-time monitoring and visualization of Post-Quantum Cryptography performance metrics. It receives performance reports from PQC analyzer scripts via UDP and presents them through an intuitive web dashboard.

## Features

- **Real-time Data Collection**: Listens on UDP port 5005 for JSON-formatted PQC metrics
- **Web Dashboard**: Interactive HTML5 dashboard for visualizing KPI data
- **RESTful API**: Provides API endpoints for programmatic access to metrics
- **Event Storage**: Maintains in-memory history of the last 50 events
- **Statistics**: Aggregates metrics by exchange type and reporting node
- **Auto-refresh**: Dashboard automatically updates every 2 seconds
- **Responsive Design**: Works on desktop and mobile devices

## Architecture

```
katana-pqc-kpi/
├── katana/
│   └── pqc_server.py          # Main Flask application and UDP listener
├── templates/
│   └── index.html              # Web dashboard
├── Dockerfile                   # Container configuration
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Configuration

### UDP Listener Configuration
- **Listen IP**: `0.0.0.0` (all interfaces)
- **Listen Port**: `5005`
- **Max History**: 50 events

### Web Server Configuration
- **Listen IP**: `0.0.0.0` (all interfaces)
- **Listen Port**: `8080`

## Installation

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the server:
```bash
cd katana-pqc-kpi
python -m katana.pqc_server
```

3. Access the dashboard:
```
http://localhost:8080
```

### Docker Deployment

Build the image:
```bash
docker build -t katana-pqc-kpi:latest .
```

Run the container:
```bash
docker run -d \
  --name katana-pqc-kpi \
  -p 8080:8080 \
  -p 5005:5005/udp \
  katana-pqc-kpi:latest
```

## API Endpoints

### GET `/`
Returns the main dashboard HTML page.

### GET `/api/events`
Returns all captured PQC KPI events in JSON format.

**Response:**
```json
[
  {
    "burst_summary": {
      "exchange_type": "KEM"
    },
    "_reporter_ip": "192.168.1.100"
  },
  ...
]
```

### GET `/api/stats`
Returns aggregated statistics about captured events.

**Response:**
```json
{
  "total_events": 42,
  "exchange_types": {
    "KEM": 25,
    "Signature": 17
  },
  "reporter_ips": {
    "192.168.1.100": 30,
    "192.168.1.101": 12
  }
}
```

### GET `/api/clear`
Clears all captured events from memory.

**Response:**
```json
{
  "status": "cleared"
}
```

## Analyzer Integration

PQC analyzer scripts should send JSON reports in the following format:

```json
{
  "burst_summary": {
    "exchange_type": "KEM|Signature|Other"
  },
  "timestamp": "2024-01-12T10:30:45.123Z",
  "metrics": {
    "key_size": 1024,
    "processing_time_ms": 42.5
  }
}
```

Send reports via UDP to the listening port:
```python
import json
import socket

report = {
    "burst_summary": {"exchange_type": "KEM"},
    "timestamp": "2024-01-12T10:30:45.123Z",
    "metrics": {"key_size": 1024}
}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(json.dumps(report).encode(), ('target_host', 5005))
```

## Monitoring and Logging

The module logs all received reports and errors to stdout. Log output includes:

- UDP listener startup
- Received report details
- JSON parsing errors
- Connection issues

Example log output:
```
2024-01-12 10:30:45,123 - pqc_server - INFO - UDP Listener active on 0.0.0.0:5005
2024-01-12 10:30:46,456 - pqc_server - INFO - Received PQC report from 192.168.1.100: KEM
```

## Performance Characteristics

- **Memory Usage**: ~50 events × event size (typically < 10MB)
- **Network Bandwidth**: Minimal (small JSON payloads over UDP)
- **CPU Usage**: Low (simple JSON parsing and HTTP serving)
- **Concurrency**: Thread-safe event storage with deque

## Troubleshooting

### Dashboard shows "No events captured"
1. Verify the analyzer is sending reports to the correct host/port
2. Check firewall rules allow UDP 5005 inbound
3. View logs to see if UDP packets are being received

### Events not persisting
By design, events are stored in memory only. Restarting the service clears all events. For persistent storage, implement a database backend.

### High memory usage
Adjust `MAX_HISTORY` in `pqc_server.py` to reduce the number of stored events.

## Future Enhancements

- [ ] Database backend for persistent storage
- [ ] Advanced filtering and search capabilities
- [ ] Export functionality (CSV, JSON)
- [ ] Alert thresholds and notifications
- [ ] Performance analytics and trending
- [ ] Multi-node aggregation
- [ ] Security enhancements (authentication, encryption)

## Dependencies

- Flask 2.0.0+
- Python 3.9+
- Standard library: socket, threading, json, collections, logging

## License

Same as Katana Slice Manager

## Contact

For issues or contributions, please refer to the main Katana project repository.
