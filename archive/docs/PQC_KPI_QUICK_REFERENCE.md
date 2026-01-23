# PQC KPI Module - Quick Reference

## 📋 Module Location
```
/katana-pqc-kpi/
```

## 🚀 Quick Start

### Docker
```bash
# Build
docker-compose build katana-pqc-kpi

# Run
docker-compose up -d katana-pqc-kpi

# View logs
docker logs katana-pqc-kpi -f

# Stop
docker-compose down
```

### Local Development
```bash
cd katana-pqc-kpi
pip install -r requirements.txt
python -m katana.pqc_server
```

## 🌐 Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| Dashboard | `http://localhost:8080/` | Web UI for visualization |
| Events API | `http://localhost:8080/api/events` | Get all events |
| Stats API | `http://localhost:8080/api/stats` | Get statistics |
| Clear API | `http://localhost:8080/api/clear` | Clear all events |
| UDP Listener | `0.0.0.0:5005` | Receive PQC reports |

## 📡 Sending Reports

### UDP Format
```python
import socket, json

report = {
    "burst_summary": {"exchange_type": "KEM"},
    "metrics": {"algorithm": "Kyber-768", "time_ms": 2.5},
    "timestamp": "2024-01-12T10:30:45.123Z"
}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(json.dumps(report).encode(), ('localhost', 5005))
```

## 📊 Dashboard Features
- Real-time event display
- Statistics cards (total events, types, nodes)
- Auto-refresh every 2 seconds
- Responsive design (mobile-friendly)
- Color-coded event types
- Reporter IP tracking

## 🔧 Configuration

| Setting | Location | Default | Purpose |
|---------|----------|---------|---------|
| UDP Listen IP | pqc_server.py | `0.0.0.0` | Listener address |
| UDP Port | pqc_server.py | `5005` | Listener port |
| HTTP Port | docker-compose | `8080` | Web dashboard |
| Max History | pqc_server.py | `50` | Events to keep |
| Refresh Rate | index.html | `2000ms` | Dashboard update |

## 📁 File Structure
```
katana-pqc-kpi/
├── katana/
│   ├── __init__.py ................. Package init
│   └── pqc_server.py ............... Main app (124 lines)
├── templates/
│   └── index.html .................. Dashboard (260 lines)
├── Dockerfile ...................... Container config
├── requirements.txt ................ Dependencies
├── README.md ....................... Full documentation
├── sample_report_generator.py ...... Test script
└── .dockerignore ................... Build excludes
```

## 🛠️ Main Components

### pqc_server.py
- `create_app()` - Flask factory function
- `udp_listener()` - Background UDP thread
- `GET /` - Serve dashboard
- `GET /api/events` - Return events
- `GET /api/stats` - Return statistics
- `GET /api/clear` - Clear history

### index.html
- Responsive dashboard
- Real-time updates
- Statistics display
- Event list with filtering
- Auto-refresh mechanism

## 🧪 Testing

### Option 1: Sample Generator
```bash
python katana-pqc-kpi/sample_report_generator.py
```

### Option 2: Manual UDP Test
```bash
python -c "
import socket, json
report = {'burst_summary': {'exchange_type': 'KEM'}}
socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(
    json.dumps(report).encode(), ('localhost', 5005)
)
"
```

### Option 3: API Test
```bash
curl http://localhost:8080/api/events
curl http://localhost:8080/api/stats
```

## 📈 Metrics Captured
- Exchange Type (KEM, Signature, Hybrid)
- Algorithm name
- Performance times (ms)
- Key sizes (bytes)
- Success/failure status
- Timestamps (UTC)
- Node IDs
- Reporter IP addresses

## ⚙️ Performance Specs
- **Memory**: ~50 events max
- **CPU**: Low (minimal processing)
- **Network**: UDP only for ingestion
- **Threads**: 2 (main + listener)
- **Concurrency**: Thread-safe

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Can't connect | Check if port 8080 is free, verify firewall |
| No events | Ensure analyzer sends to `localhost:5005` (UDP) |
| High memory | Reduce `MAX_HISTORY` in pqc_server.py |
| Slow updates | Dashboard auto-refreshes every 2 seconds |
| JSON errors | Verify report format matches specification |

## 📚 Documentation Files
- `katana-pqc-kpi/README.md` - Full module documentation
- `INTEGRATION_GUIDE_PQC_KPI.md` - Integration guide
- `PQC_KPI_IMPLEMENTATION_SUMMARY.md` - Implementation details

## 🔗 Integration Points
- Integrated into `docker-compose.yaml`
- Ports: 8080 (HTTP), 5005 (UDP)
- Service name: `katana-pqc-kpi`
- Container name: `katana-pqc-kpi`

## 💡 Quick Customization

### Change HTTP Port
1. Edit `docker-compose.yaml`: `- "9000:8080"`
2. Edit `Dockerfile` if needed

### Change UDP Port
1. Edit `pqc_server.py`: `UDP_LISTEN_PORT = 5006`
2. Update `docker-compose.yaml`: `- "5006:5006/udp"`

### Increase Event History
1. Edit `pqc_server.py`: `MAX_HISTORY = 100`
2. Rebuild and restart

### Change Refresh Rate
1. Edit `index.html`: `const AUTO_REFRESH_INTERVAL = 3000;` (in milliseconds)

## 🚀 Deployment Checklist
- [ ] Docker image builds: `docker-compose build katana-pqc-kpi`
- [ ] Service starts: `docker-compose up -d katana-pqc-kpi`
- [ ] Dashboard loads: `curl http://localhost:8080`
- [ ] API responds: `curl http://localhost:8080/api/stats`
- [ ] Test reports: `python sample_report_generator.py`
- [ ] View logs: `docker logs katana-pqc-kpi`

## 📞 Support
1. Check module README.md
2. Review INTEGRATION_GUIDE_PQC_KPI.md
3. Check service logs: `docker logs katana-pqc-kpi`
4. Test with sample_report_generator.py
5. Verify network connectivity

---

**Version**: 1.0.0 | **Status**: Production Ready
**Last Updated**: January 2024
