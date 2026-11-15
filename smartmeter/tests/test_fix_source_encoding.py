"""Tests for ``fix_source_encoding`` (Python 3.15 vs. gurux-dlms, #128)."""

from __future__ import annotations

from pathlib import Path

from fix_source_encoding import fix_directory

LATIN1_COMMENT = "x = 1  # näyttää myös\n"


def test_latin1_file_is_converted_to_utf8(tmp_path: Path) -> None:
    bad = tmp_path / "pkg" / "objects" / "bad.py"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(LATIN1_COMMENT.encode("latin-1"))

    assert fix_directory(tmp_path) == [bad]
    assert bad.read_bytes().decode("utf-8") == LATIN1_COMMENT
    compile(bad.read_bytes(), str(bad), "exec")


def test_utf8_files_are_left_untouched(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    good.write_bytes(LATIN1_COMMENT.encode("utf-8"))
    before = good.stat().st_mtime_ns

    assert fix_directory(tmp_path) == []
    assert good.read_bytes() == LATIN1_COMMENT.encode("utf-8")
    assert good.stat().st_mtime_ns == before
