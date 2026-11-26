"""RAMVORA rebrand: public branding updated, nothing that existed before breaks."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import backup
from app.ai_extraction import ai_enabled
from app.main import app
from app.security import create_api_key, init_db


def test_public_branding(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "b.db"))
    with TestClient(app) as client:
        root = client.get("/").json()
        assert root["name"] == "RAMVORA Invoice Intelligence API"
        assert root["tagline"] == "Built for what's next."
        assert client.get("/health").json() == {"status": "ok", "service": "ramvora-api"}
        assert client.get("/openapi.json").json()["info"]["title"] == "RAMVORA Invoice Intelligence API"
        page = client.get("/dashboard").text
        assert "<title>RAMVORA" in page and "Quillvora" not in page


def test_api_key_prefix_and_endpoints_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "k.db"))
    init_db()
    key, _ = create_api_key("existing customer", 10)
    assert key.startswith("iia_")  # existing integrations and key scanners keep working
    with TestClient(app) as client:
        assert client.get("/v1/usage", headers={"Authorization": f"Bearer {key}"}).status_code == 200


def test_legacy_ai_setting_still_honoured(monkeypatch):
    monkeypatch.delenv("RAMVORA_AI_ENABLED", raising=False)
    monkeypatch.setenv("QUILLVORA_AI_ENABLED", "true")
    assert ai_enabled() is True
    monkeypatch.delenv("QUILLVORA_AI_ENABLED")
    assert ai_enabled() is False


def test_legacy_backups_are_still_recognised_and_pruned(tmp_path, monkeypatch):
    key = __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode()
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", key)
    db = tmp_path / "db.sqlite3"
    import sqlite3
    sqlite3.connect(db).execute("create table t(x)").connection.commit()
    now = datetime.now(timezone.utc)
    old = backup.create_backup(db, tmp_path / "bk", key=key, now=now - timedelta(days=400))
    legacy = old.path.with_name(old.path.name.replace("ramvora-", "quillvora-"))
    old.path.rename(legacy)
    old.path.with_name(old.path.name + ".json").rename(legacy.with_name(legacy.name + ".json"))
    new = backup.create_backup(db, tmp_path / "bk", key=key, now=now)
    assert backup._backup_time(legacy) is not None
    removed = backup.prune_backups(tmp_path / "bk", keep_daily=1, keep_weekly=0, keep_monthly=0)
    assert removed == [legacy.name] and new.path.exists()
    # A legacy backup can still be restored.
    restored = tmp_path / "restored.db"
    legacy2 = backup.create_backup(db, tmp_path / "bk2", key=key, now=now).path
    renamed = legacy2.with_name(legacy2.name.replace("ramvora-", "quillvora-"))
    legacy2.rename(renamed)
    assert backup.restore_backup(renamed, restored, key=key, expected_sha256=None).exists()


def test_legal_entity_unchanged():
    terms = open("TERMS_DRAFT.md", encoding="utf-8").read()
    assert "Divine Group Holdings LLC" in terms and "doing business as RAMVORA" in terms
