from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import Database


class BackupService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def create(self) -> dict[str, Any]:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = self.settings.backup_dir / f"jarvis-backup-{timestamp}.zip"
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "jarvis.db"
            source = sqlite3.connect(self.db.path)
            destination = sqlite3.connect(snapshot)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            manifest = {
                "created_at": datetime.now(UTC).isoformat(),
                "schema_version": self.db.get_setting("schema_version", 1),
                "contents": ["jarvis.db"],
                "master_key_included": False,
            }
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "jarvis.db")
                archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        return {"path": str(output), "sha256": digest, "bytes": output.stat().st_size}

    def list(self) -> list[dict[str, Any]]:
        items = []
        for path in sorted(self.settings.backup_dir.glob("jarvis-backup-*.zip"), reverse=True):
            items.append({"name": path.name, "bytes": path.stat().st_size})
        return items
