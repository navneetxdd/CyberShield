from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
app_root_str = str(APP_ROOT)

if app_root_str not in sys.path:
    sys.path.insert(0, app_root_str)
