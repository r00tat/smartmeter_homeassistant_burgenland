"""Fail if the integration does not pin the library version of this commit.

The integration installs the reader core from PyPI (``smartmeter-austria``);
the release workflow sets the library version and the manifest pin to the
release tag. Between releases both must still agree, otherwise a HACS
install of this commit would load a different library than the one tested.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = "smartmeter-austria"


def main() -> int:
    """Compare the manifest pin with the library version and return an exit code."""
    pyproject = tomllib.loads(
        (ROOT / "packages/smartmeter-austria/pyproject.toml").read_text()
    )
    version = pyproject["project"]["version"]
    manifest = json.loads(
        (ROOT / "custom_components/smartmeter_at/manifest.json").read_text()
    )
    expected = f"{LIBRARY}=={version}"
    pins = [req for req in manifest["requirements"] if req.startswith(f"{LIBRARY}")]
    if pins != [expected]:
        print(f"manifest.json requirements {manifest['requirements']} lack {expected!r}")
        return 1
    if manifest["version"] != version:
        print(f"manifest.json version {manifest['version']} != library version {version}")
        return 1
    print(f"integration pins {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
