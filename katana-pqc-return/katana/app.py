import logging
from flask import Flask, jsonify, redirect
from flask_cors import CORS
from .endpoint import LogsView  # Import your custom LogsView

def create_app():
    """
    Create a Flask application for a web interface that displays logs.
    """
    # Explicitly specify the template folder.
    app = Flask(__name__, template_folder='templates', instance_relative_config=True)
    
    # Enable CORS if needed.
    CORS(app)

    # Setup logging.
    logger = logging.getLogger("katana")
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("Katana web interface started successfully.")

    # Redirect root URL to /logs/view.
    @app.route('/')
    def index():
        return redirect('/logs/view')

    # Register your custom LogsView.
    LogsView.register(app, trailing_slash=False)

    # Error handlers returning JSON.
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def server_error(error):
        return jsonify({"error": "Internal server error"}), 500

    print(">>> URL MAP:", app.url_map)
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=4443, debug=True)
