from __future__ import annotations

import zipfile


def test_backup_contains_database_not_master_key(application):
    application.memory.remember("backup me")
    result = application.backups.create()
    with zipfile.ZipFile(result["path"]) as archive:
        names = archive.namelist()
    assert "jarvis.db" in names
    assert "manifest.json" in names
    assert "master.key" not in names
