"""
Root-level launcher for CyberShield AI Video Analytics.

Run from the workspace root:
    python run.py

The server starts on http://localhost:8080
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent / "integrated-video-analytics"
APP_PYTHON = APP_DIR / ".venv" / "Scripts" / "python.exe"

if not APP_PYTHON.exists():
    # Fallback to the current interpreter (e.g. in CI)
    APP_PYTHON = Path(sys.executable)

# Change into the app directory so uvicorn reload and relative paths work correctly.
os.chdir(APP_DIR)
os.execv(str(APP_PYTHON), [str(APP_PYTHON), str(APP_DIR / "main.py")])
