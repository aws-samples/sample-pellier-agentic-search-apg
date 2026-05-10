"""
Shared types for Pellier MCP servers.
Minimal version — deploy_lambda.py expects this file to exist.
"""
from typing import Optional


class IdentityContext:
    """User identity from Cognito JWT."""
    def __init__(self, username: str = "", sub: str = "", email: str = None):
        self.username = username
        self.sub = sub
        self.email = email
