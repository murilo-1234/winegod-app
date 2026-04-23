"""Pytest config para sdk/tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Permite importar winegod_scraper_sdk sem pip install.
SDK_ROOT = Path(__file__).resolve().parent.parent
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))
