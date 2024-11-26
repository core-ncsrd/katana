""" Katana North-Bound Interface - Implemented with Flask"""

# -*- coding: utf-8 -*-
from flask import Flask
from flask_cors import CORS

from katana.api.ems import EmsView
from katana.api.function import FunctionView
from katana.api.gst import GstView
from katana.api.nfvo import NFVOView
from katana.api.nslist import NslistView
from katana.api.policy import PolicyView
from katana.api.resource import ResourcesView
from katana.api.slice import SliceView
from katana.api.slice_des import Base_slice_desView
from katana.api.vim import VimView
from katana.api.wim import WimView
from katana.api.bootstrap import BootstrapView
from katana.api.locations import LocationView
from katana.api.alerts import AlertView


def create_app():
    """
    Create a Flask application using the app factory pattern.

    :return: Flask app
    """
    app = Flask(__name__, instance_relative_config=True)

    # Enable CORS for the app
    CORS(app)

    app.config.from_object("config.settings")
    app.config.from_pyfile("settings.py", silent=True)

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

    return app
