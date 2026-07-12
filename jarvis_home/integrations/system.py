from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from ..config import Settings


class SandboxViolation(PermissionError):
    pass


class FileSandbox:
    def __init__(self, roots: list[Path]):
        self.roots = [root.resolve() for root in roots]

    def resolve(self, path: str) -> Path:
        if not self.roots:
            raise SandboxViolation("No workspace roots are configured")
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.roots[0] / candidate
        resolved = candidate.resolve(strict=False)
        for root in self.roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise SandboxViolation(f"Path escapes configured workspace roots: {path}")

    def list_directory(self, path: str = ".", limit: int = 200) -> list[dict[str, Any]]:
        resolved = self.resolve(path)
        if not resolved.exists() or not resolved.is_dir():
            raise FileNotFoundError(path)
        entries: list[dict[str, Any]] = []
        for item in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:limit]:
            try:
                stat = item.stat()
                entries.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "kind": "directory" if item.is_dir() else "file",
                        "size": stat.st_size,
                    }
                )
            except OSError:
                continue
        return entries

    def read_text(self, path: str, max_bytes: int = 200_000) -> str:
        resolved = self.resolve(path)
        if not resolved.is_file():
            raise FileNotFoundError(path)
        size = resolved.stat().st_size
        if size > max_bytes:
            raise ValueError(f"File is too large ({size} bytes; limit {max_bytes})")
        data = resolved.read_bytes()
        if b"\x00" in data:
            raise ValueError("Binary files cannot be read by this tool")
        return data.decode("utf-8", errors="replace")

    def write_text(self, path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
        resolved = self.resolve(path)
        if resolved.exists() and not overwrite:
            raise FileExistsError("File exists; set overwrite=true after reviewing the target")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        temp = resolved.with_suffix(resolved.suffix + ".jarvis.tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, resolved)
        return {"path": str(resolved), "bytes": len(content.encode("utf-8"))}

    def search_text(self, query: str, path: str = ".", limit: int = 50) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        root = self.resolve(path)
        results: list[dict[str, Any]] = []
        needle = query.casefold()
        for file in root.rglob("*"):
            if len(results) >= limit:
                break
            if not file.is_file() or file.stat().st_size > 1_000_000:
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if needle in line.casefold():
                    results.append({"path": str(file), "line": number, "text": line[:500]})
                    if len(results) >= limit:
                        break
        return results


class ShellRunner:
    def __init__(self, settings: Settings, sandbox: FileSandbox):
        self.settings = settings
        self.sandbox = sandbox

    def run(self, command: str, cwd: str = ".", timeout_seconds: int = 30) -> dict[str, Any]:
        if not self.settings.enable_shell:
            raise SandboxViolation("Shell execution is disabled")
        argv = shlex.split(command, posix=os.name != "nt")
        if not argv:
            raise ValueError("Empty command")
        executable = Path(argv[0]).name.lower()
        if executable not in self.settings.shell_allowlist_set:
            raise SandboxViolation(f"Executable is not allowlisted: {executable}")
        working_dir = self.sandbox.resolve(cwd)
        result = subprocess.run(  # noqa: S603
            argv,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=min(max(timeout_seconds, 1), 120),
            shell=False,
            env={
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            },
            check=False,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-50_000:],
            "stderr": result.stderr[-50_000:],
        }
