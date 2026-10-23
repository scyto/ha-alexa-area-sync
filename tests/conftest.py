"""Run the pure planning logic without installing Home Assistant.

sync.py imports a few Home Assistant modules at import time; the functions tested
here (reconcile, member_serial, device_label) never call them, so stubs are enough.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

for name in [
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.helpers",
    "homeassistant.helpers.area_registry",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.floor_registry",
]:
    sys.modules.setdefault(name, MagicMock())

pkg = types.ModuleType("alexa_area_sync")
pkg.__path__ = [str(Path(__file__).parent.parent / "custom_components" / "alexa_area_sync")]
sys.modules["alexa_area_sync"] = pkg
