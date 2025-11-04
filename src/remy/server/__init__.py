"""ASGI application factory and dependencies for the Remy server."""

from remy.server.app import app, create_app

__all__ = ["app", "create_app"]
