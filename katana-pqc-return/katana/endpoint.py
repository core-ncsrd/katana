import logging
from flask import request, jsonify, render_template
from flask_classful import FlaskView
from datetime import datetime  # Import datetime for timestamps

logger = logging.getLogger(__name__)

# Shared list to store logs
received_logs = []

class LogsView(FlaskView):
    route_prefix = '/logs'
    route_base = ''  # This removes the extra segment from the URL

    def post(self):
        """
        Accepts JSON logs and processes them.
        Expects a JSON payload with keys: tx_id, metrics_hash, and mongo_id.
        """
        if request.is_json:
            data = request.get_json()
            tx_id = data.get('tx_id')
            metrics_hash = data.get('metrics_hash')
            mongo_id = data.get('mongo_id')
            metrics_Data = data.get('MetricsData')  # Optional metrics data
            logger.info("Received JSON log: TX ID: %s, Metrics Hash: %s, Mongo ID: %s",
                        tx_id, metrics_hash, mongo_id)
            
            # Add the received log to the shared list
            received_logs.append({
                "tx_id": tx_id,
                "metrics_hash": metrics_hash,
                "mongo_id": mongo_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Add actual timestamp
                  # Optional metrics data
            })
            
            return jsonify({
                "message": "JSON log received successfully",
                "tx_id": tx_id,
                "metrics_hash": metrics_hash,
                "mongo_id": mongo_id
            }), 200
        else:
            return jsonify({"error": "No valid log data received"}), 400

    def view(self):
        """
        Renders an HTML template displaying logs.
        This is a GET endpoint that returns a GUI for logs.
        """
        return render_template('logs.html')

    def get_logs(self):
        """
        Returns the logs as JSON for the frontend to fetch.
        """
        return jsonify(received_logs), 200
