"""Make the library's test helpers importable for the add-on tests.

The serial test doubles and sample telegrams live with the library tests in
``packages/smartmeter-austria/tests``; the end-to-end tests of the add-on
replay the same telegrams through the MQTT bridge.
"""

from __future__ import annotations

import sys
from pathlib import Path

LIBRARY_TESTS = Path(__file__).resolve().parents[2] / "packages/smartmeter-austria/tests"
sys.path.insert(0, str(LIBRARY_TESTS))
