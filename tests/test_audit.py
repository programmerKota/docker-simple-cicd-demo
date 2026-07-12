from __future__ import annotations


def test_audit_chain_detects_tampering(application):
    application.audit.record("alice", "one", "resource", "success", {"x": 1})
    application.audit.record("alice", "two", "resource", "success", {"x": 2})
    assert application.audit.verify_chain() == (True, None)
    with application.db.transaction() as conn:
        conn.execute("UPDATE audit_log SET outcome='tampered' WHERE id=1")
    ok, broken_at = application.audit.verify_chain()
    assert not ok
    assert broken_at == 1
