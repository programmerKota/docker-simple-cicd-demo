from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_home.integrations.system import FileSandbox, SandboxViolation


def test_sandbox_read_write(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    sandbox = FileSandbox([root])
    result = sandbox.write_text("notes/test.txt", "hello")
    assert result["bytes"] == 5
    assert sandbox.read_text("notes/test.txt") == "hello"
    assert sandbox.search_text("hell")[0]["line"] == 1


def test_sandbox_blocks_escape(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    sandbox = FileSandbox([root])
    with pytest.raises(SandboxViolation):
        sandbox.resolve("../outside.txt")
