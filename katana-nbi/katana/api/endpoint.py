import logging
import os
from logging import handlers
from flask import request, jsonify, render_template
from flask_classful import FlaskView

# Logging Parameters
logger = logging.getLogger(__name__)
file_handler = handlers.RotatingFileHandler("katana.log", maxBytes=10000, backupCount=5)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(stream_handler)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

class LogsView(FlaskView):
    route_prefix = '/logs'  # All routes will be prefixed with /logs

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
            logger.info("Received JSON log: TX ID: %s, Metrics Hash: %s, Mongo ID: %s", tx_id, metrics_hash, mongo_id)
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
        # Normally, you would retrieve logs from a database or log storage.
        # For demonstration, we use a static list of logs.
        logs = [
            {"tx_id": "123", "metrics_hash": "abc", "mongo_id": "456", "timestamp": "2025-03-20 10:00:00"},
            {"tx_id": "789", "metrics_hash": "def", "mongo_id": "012", "timestamp": "2025-03-20 10:05:00"}
        ]
        return render_template('logs.html', logs=logs)
