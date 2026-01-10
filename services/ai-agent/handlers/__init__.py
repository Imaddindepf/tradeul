"""
Request Handlers
================
Separated handlers for WebSocket and REST endpoints.
"""

from .websocket import WebSocketHandler
from .rest import create_rest_routes

__all__ = ["WebSocketHandler", "create_rest_routes"]
