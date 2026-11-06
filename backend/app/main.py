"""
Compatibility re-export module for backend.app.main:app.
Delegates to the modular backend.main:app.
"""
from backend.main import app

__all__ = ["app"]
