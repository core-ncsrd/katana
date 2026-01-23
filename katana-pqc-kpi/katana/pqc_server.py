"""
PQC KPI Monitoring Web Server
Listens for Post-Quantum Cryptography metrics reports via UDP
and provides a web interface for monitoring and analysis.
"""
from flask import Flask, render_template, jsonify
import socket
import threading
import json
import collections
import logging
import os
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
UDP_LISTEN_IP = "0.0.0.0"
UDP_LISTEN_PORT = 5005
MAX_HISTORY = 50  # Keep last 50 events in memory

# Store events in a thread-safe list
captured_events = collections.deque(maxlen=MAX_HISTORY)

def create_app():
    """
    Create a Flask application for PQC KPI monitoring.
    """
    # Get template directory - works both in container and locally
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    app = Flask(__name__, template_folder=template_dir)

    @app.route('/')
    def index():
        """Serve the main dashboard."""
        return render_template('index.html')

    @app.route('/api/events')
    def get_events():
        """Get all captured PQC KPI events."""
        return jsonify(list(captured_events))

    @app.route('/api/clear')
    def clear_events():
        """Clear all captured events."""
        captured_events.clear()
        logger.info("Cleared all PQC KPI events")
        return jsonify({"status": "cleared"})

    @app.route('/api/stats')
    def get_stats():
        """Get statistics about captured events."""
        if not captured_events:
            return jsonify({
                "total_events": 0,
                "exchange_types": {},
                "algorithms": {},
                "reporter_ips": {},
                "total_bytes": 0,
                "fragmented_count": 0,
                "avg_key_size": 0
            })
        
        exchange_types = {}
        algorithms = {}
        reporter_ips = {}
        total_bytes = 0
        fragmented_count = 0
        total_key_sizes = []
        
        for event in captured_events:
            # Exchange type
            exchange_type = event.get('burst_summary', {}).get('exchange_type', 'unknown')
            exchange_types[exchange_type] = exchange_types.get(exchange_type, 0) + 1
            
            # Algorithm
            algorithm = event.get('identified_pqc_algorithm', 'Unknown')
            algorithms[algorithm] = algorithms.get(algorithm, 0) + 1
            
            # Reporter IP
            reporter_ip = event.get('_reporter_ip', 'unknown')
            reporter_ips[reporter_ip] = reporter_ips.get(reporter_ip, 0) + 1
            
            # Fragmentation
            if event.get('burst_summary', {}).get('is_fragmented'):
                fragmented_count += 1
            
            # Sizes
            key_size = event.get('burst_summary', {}).get('total_key_size')
            if isinstance(key_size, str):
                try:
                    key_size = int(key_size)
                except:
                    key_size = 0
            if key_size:
                total_bytes += key_size
                total_key_sizes.append(key_size)
        
        avg_key_size = sum(total_key_sizes) / len(total_key_sizes) if total_key_sizes else 0
        
        return jsonify({
            "total_events": len(captured_events),
            "exchange_types": exchange_types,
            "algorithms": algorithms,
            "reporter_ips": reporter_ips,
            "total_bytes": int(total_bytes),
            "fragmented_count": fragmented_count,
            "avg_key_size": int(avg_key_size)
        })

    return app

def udp_listener():
    """Background thread to receive JSON reports from the PQC analyzer script."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_LISTEN_IP, UDP_LISTEN_PORT))
    logger.info(f"UDP Listener active on {UDP_LISTEN_IP}:{UDP_LISTEN_PORT}")
    
    while True:
        try:
            data, addr = sock.recvfrom(65535)
            json_str = data.decode('utf-8')
            report = json.loads(json_str)
            
            # Add metadata about where it came from
            report['_reporter_ip'] = addr[0]
            
            # Prepend to list (newest first)
            captured_events.appendleft(report)
            exchange_type = report.get('burst_summary', {}).get('exchange_type', 'unknown')
            logger.info(f"Received PQC report from {addr[0]}: {exchange_type}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from {addr[0]}: {e}")
        except Exception as e:
            logger.error(f"Error processing UDP packet: {e}")

def start_server(host='0.0.0.0', port=8080, debug=False):
    """
    Start the PQC KPI monitoring web server.
    
    Args:
        host: IP address to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8080)
        debug: Enable Flask debug mode (default: False)
    """
    # Start the UDP listener in a background thread
    listener_thread = threading.Thread(target=udp_listener, daemon=True)
    listener_thread.start()
    
    # Create and start the Flask app
    app = create_app()
    logger.info(f"Web Interface running at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)

if __name__ == '__main__':
    # Get host and port from environment or use defaults
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 8080))
    start_server(host=host, port=port, debug=False)
