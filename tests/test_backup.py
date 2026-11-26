"""Encrypted backup, retention, offsite upload and a real restore round trip."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import backup
from app.main import app
from app.security import create_api_key, get_key_record, init_db, set_subscription

ADMIN = {"X-Admin-Key": "admin-key-for-tests-0123456789abcdefghijkl", "X-Admin-Actor": "ops"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "live" / "invoice_api.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("BACKUP_S3_BUCKET", raising=False)
    init_db()
    key, meta = create_api_key("secret-customer@example.com", 500)
    set_subscription(meta["id"], "starter", "active", "cus_backup", "sub_backup", 500)
    return {"db": db, "dir": tmp_path / "backups", "key": key, "tmp": tmp_path}


def test_backup_is_encrypted_and_restores_exactly(env):
    result = backup.run_backup()
    raw = result.path.read_bytes()
    assert b"secret-customer@example.com" not in raw and b"cus_backup" not in raw
    assert b"SQLite format" not in raw
    manifest = json.loads(result.path.with_name(result.path.name + ".json").read_text())
    assert manifest["sha256"] == result.sha256
    assert oct(result.path.stat().st_mode & 0o777) == "0o600"

    restored = backup.restore_backup(result.path, env["tmp"] / "restored" / "db.sqlite3")
    with sqlite3.connect(restored) as conn:
        row = conn.execute("SELECT label,stripe_customer_id,key_hash FROM api_keys").fetchone()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert row[0] == "secret-customer@example.com" and row[1] == "cus_backup"
    assert row[2] != env["key"]  # only the hash is stored, never the raw key


def test_restore_refuses_wrong_key_tampering_and_overwrite(env, monkeypatch):
    result = backup.run_backup()
    with pytest.raises(backup.BackupError, match="decrypted"):
        backup.restore_backup(result.path, env["tmp"] / "x.db", key=Fernet.generate_key().decode())

    tampered = env["tmp"] / result.path.name
    data = bytearray(result.path.read_bytes())
    data[-5] ^= 1
    tampered.write_bytes(bytes(data))
    tampered.with_name(tampered.name + ".json").write_text(
        result.path.with_name(result.path.name + ".json").read_text())
    with pytest.raises(backup.BackupError, match="checksum"):
        backup.restore_backup(tampered, env["tmp"] / "y.db")

    with pytest.raises(backup.BackupError, match="already exists"):
        backup.restore_backup(result.path, env["db"])


def test_forced_restore_preserves_previous_database(env):
    result = backup.run_backup()
    create_api_key("added-after-backup@example.com", 10)
    backup.restore_backup(result.path, env["db"], force=True)
    preserved = list(env["db"].parent.glob("invoice_api.db.pre-restore-*"))
    assert len(preserved) == 1
    with sqlite3.connect(env["db"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] == 1
    with sqlite3.connect(preserved[0]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] == 2
    assert get_key_record(env["key"])["stripe_customer_id"] == "cus_backup"


def test_backup_key_must_differ_from_api_key_encryption_key(env, monkeypatch):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    import os
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", os.environ["BACKUP_ENCRYPTION_KEY"])
    with pytest.raises(backup.BackupError, match="different"):
        backup.run_backup()
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY")
    with pytest.raises(backup.BackupError, match="not configured"):
        backup.run_backup()


def test_retention_keeps_daily_weekly_monthly(tmp_path):
    start = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
    paths = [tmp_path / f"ramvora-{(start + timedelta(days=d)).strftime('%Y%m%dT%H%M%S%fZ')}.sqlite3.gz.enc"
             for d in range(120)]
    keep = backup.select_retained(paths, keep_daily=7, keep_weekly=4, keep_monthly=3)
    newest = paths[-1]
    assert newest in keep
    assert set(paths[-7:]) <= keep            # last 7 days
    assert len(keep) <= 7 + 4 + 3
    months = {datetime.strptime(p.name[8:30], "%Y%m%dT%H%M%S%fZ").month for p in keep}
    assert len(months) >= 3


def test_prune_removes_old_files_and_manifests(env):
    for days in range(10, 0, -1):
        backup.create_backup(env["db"], env["dir"], now=datetime.now(timezone.utc) - timedelta(days=days * 40))
    removed = backup.prune_backups(env["dir"], keep_daily=2, keep_weekly=0, keep_monthly=0)
    remaining = sorted(env["dir"].glob("*.enc"))
    assert len(remaining) == 2 and len(removed) == 8
    assert len(list(env["dir"].glob("*.json"))) == 2


def test_offsite_upload_sends_backup_and_manifest(env, monkeypatch):
    monkeypatch.setenv("BACKUP_S3_BUCKET", "qv-backups")
    monkeypatch.setenv("BACKUP_S3_PREFIX", "staging/")
    calls = []

    class FakeS3:
        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            calls.append((Path(filename).name, bucket, key, ExtraArgs))

    result = backup.run_backup(client=FakeS3())
    assert result.uploaded_to == f"s3://qv-backups/staging/{result.path.name}"
    assert [c[2] for c in calls] == [f"staging/{result.path.name}", f"staging/{result.path.name}.json"]
    assert calls[0][3]["Metadata"]["sha256"] == result.sha256


def test_cli_verify_and_admin_endpoints(env, monkeypatch, capsys):
    result = backup.run_backup()
    assert backup._main(["verify", str(result.path)]) == 0
    assert '"api_keys": 1' in capsys.readouterr().out

    monkeypatch.setenv("API_ADMIN_KEY", ADMIN["X-Admin-Key"])
    with TestClient(app) as client:
        ran = client.post("/v1/admin/backups/run", headers=ADMIN)
        assert ran.status_code == 200 and ran.json()["backup"]["file"].endswith(".sqlite3.gz.enc")
        status = client.get("/v1/admin/backups", headers=ADMIN).json()
        assert status["encryption_configured"] is True
        assert status["runs"][0]["success"] == 1
        monkeypatch.delenv("BACKUP_ENCRYPTION_KEY")
        failed = client.post("/v1/admin/backups/run", headers=ADMIN)
        assert failed.status_code == 503
        assert client.get("/v1/admin/backups", headers=ADMIN).json()["runs"][0]["success"] == 0
