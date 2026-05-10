"""Pytest configuration for backend tests.

Ensures the backend package directory is importable so test modules can
`from models import ...`, `from services.X import ...`, etc.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_backend_str = str(_BACKEND_ROOT)
if _backend_str not in sys.path:
    sys.path.insert(0, _backend_str)
