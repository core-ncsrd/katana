import logging
from flask import Flask, jsonify
from flask_cors import CORS
from katana.api import (
    EmsView,
    FunctionView,
    GstView,
    NFVOView,
    NslistView,
    PolicyView,
    ResourcesView,
    SliceView,
    Base_slice_desView,
    VimView,
    WimView,
    BootstrapView,
    LocationView,
    AlertView,
    K8SClusterView,
    LoTView,
    InitSGCView,
    getTrustLevelView,
    PaoAlertView,
)

def create_app():
    """
    Create a Flask application using the app factory pattern.
    """
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration
    app.config.from_object("config.settings")
    app.config.from_pyfile("settings.py", silent=True)

    # Enable CORS with restrictions
    CORS(app, resources={r"/api/*": {"origins": "*"}})  # Adjust origins for production

    # Register views
    VimView.register(app, trailing_slash=False)
    WimView.register(app, trailing_slash=False)
    EmsView.register(app, trailing_slash=False)
    NFVOView.register(app, trailing_slash=False)
    SliceView.register(app, trailing_slash=False)
    FunctionView.register(app, trailing_slash=False)
    Base_slice_desView.register(app, trailing_slash=False)
    GstView.register(app, trailing_slash=False)
    ResourcesView.register(app, trailing_slash=False)
    PolicyView.register(app, trailing_slash=False)
    NslistView.register(app, trailing_slash=False)
    BootstrapView.register(app, trailing_slash=False)
    LocationView.register(app, trailing_slash=False)
    AlertView.register(app, trailing_slash=False)
    LoTView.register(app, trailing_slash=False)
    K8SClusterView.register(app, trailing_slash=False)
    InitSGCView.register(app, trailing_slash=False)
    getTrustLevelView.register(app, trailing_slash=False)
    PaoAlertView.register(app, trailing_slash=False)

    # Setup logging
    logger = logging.getLogger("katana")
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info(f"Registered routes: {app.url_map}")

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def server_error(error):
        return jsonify({"error": "Internal server error"}), 500

    logger.info("Katana application started successfully.")
    return app
