"""Fail if manifest.json pins gurux differently from smartmeter/requirements.txt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINNED = ("gurux-common", "gurux-dlms")


def pins(lines: list[str]) -> dict[str, str]:
    """Return the gurux pins found in requirement lines."""
    result = {}
    for line in lines:
        name, sep, version = line.strip().partition("==")
        if sep and name in PINNED:
            result[name] = version
    return result


def main() -> int:
    """Compare the add-on and integration pins and return an exit code."""
    addon = pins((ROOT / "smartmeter/requirements.txt").read_text().splitlines())
    manifest = json.loads(
        (ROOT / "custom_components/smartmeter_at/manifest.json").read_text()
    )
    integration = pins(manifest["requirements"])
    if addon != integration:
        print(f"gurux pins differ: add-on {addon}, integration {integration}")
        return 1
    print(f"gurux pins in sync: {addon}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
