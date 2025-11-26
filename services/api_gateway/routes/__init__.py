# Routes package
from .user_prefs import router as user_prefs_router
from .financials import router as financials_router

__all__ = ['user_prefs_router', 'financials_router']
