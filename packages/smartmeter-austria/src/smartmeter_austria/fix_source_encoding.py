"""Re-encode non-UTF-8 source files of installed packages to UTF-8.

gurux-dlms 1.0.197 ships ``objects/GXDLMSObjectCollection.py`` with a Latin-1
encoded comment and no encoding declaration. Python up to 3.14 tolerated
invalid UTF-8 inside comments, Python 3.15 rejects the file with a
``SyntaxError`` and ``import gurux_dlms`` fails, so the add-on did not start
on the current Home Assistant base image (#128).

Usage (at image build time, after ``pip install``)::

    python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def fix_directory(root: Path) -> list[Path]:
    """Convert every ``*.py`` file below ``root`` that is not valid UTF-8."""
    fixed: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            path.write_bytes(raw.decode("latin-1").encode("utf-8"))
            fixed.append(path)
    return fixed


def package_dirs(name: str) -> list[Path]:
    """Return the source directories of ``name`` without importing it."""
    spec = importlib.util.find_spec(name)
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(f"package {name!r} not found")
    return [Path(location) for location in spec.submodule_search_locations]


def main(names: list[str]) -> None:
    """Fix the given installed packages."""
    for name in names:
        for directory in package_dirs(name):
            for path in fix_directory(directory):
                print(f"re-encoded {path} from latin-1 to utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
