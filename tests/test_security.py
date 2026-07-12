from __future__ import annotations

from jarvis_home.security import AuthError


def test_authentication_and_token(application):
    user = application.security.authenticate("admin", "correct-horse-battery-staple")
    token = application.security.issue_token(user)
    decoded = application.security.verify_token(token)
    assert decoded.username == "admin"
    assert decoded.role == "owner"


def test_bad_password_rejected(application):
    try:
        application.security.authenticate("admin", "wrong")
    except AuthError:
        pass
    else:
        raise AssertionError("Bad password was accepted")


def test_secret_store_encrypts_at_rest(application):
    application.secrets.set("sample", "top-secret-value")
    row = application.db.query_one("SELECT ciphertext FROM secrets WHERE key='sample'")
    assert row is not None
    assert b"top-secret-value" not in row["ciphertext"]
    assert application.secrets.get("sample") == "top-secret-value"
