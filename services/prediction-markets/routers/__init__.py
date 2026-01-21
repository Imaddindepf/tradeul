"""Prediction Markets API Routers"""
from .admin import router as admin_router, set_config_manager

__all__ = ["admin_router", "set_config_manager"]
