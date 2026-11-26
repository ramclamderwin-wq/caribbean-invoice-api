"""Encrypted SQLite backups with retention, offsite upload and verified restore.

Why it runs inside the web service: a Render persistent disk can be attached to
only one service, so a separate cron job cannot read the database. When
``BACKUP_ENABLED=true`` the API schedules a backup every
``BACKUP_INTERVAL_HOURS`` (default 24). Operators can also run
``python -m scripts.backup_db`` in the service shell, or call the admin endpoint.

Each backup:
1. takes a consistent snapshot with SQLite's online backup API (safe while the
   service is writing);
2. checks ``PRAGMA integrity_check``;
3. gzips and encrypts it with ``BACKUP_ENCRYPTION_KEY`` (Fernet: AES-128-CBC +
   HMAC-SHA256). That key must differ from ``API_KEY_ENCRYPTION_KEY`` and must
   be stored away from the backups (e.g. a password manager);
4. writes ``ramvora-<UTC timestamp>.sqlite3.gz.enc`` plus a SHA-256 manifest
   to ``BACKUP_DIR``;
5. optionally uploads both to S3-compatible storage (``BACKUP_S3_*``);
6. prunes local copies: keep the newest daily, weekly and monthly backups.

The database stores API keys only as SHA-256 hashes (plus Fernet-encrypted
copies awaiting email delivery), but it does hold customer emails and Stripe
IDs, so backups are always encrypted before leaving the process.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("invoice_api.backup")
SUFFIX = ".sqlite3.gz.enc"
PREFIX = "ramvora-"
# Backups written before the RAMVORA rebrand keep their old name; they are still
# recognised for retention, listing and restore.
LEGACY_PREFIXES = ("quillvora-",)
_ALL_PREFIXES = (PREFIX, *LEGACY_PREFIXES)


class BackupError(RuntimeError):
    pass


@dataclass
class BackupResult:
    path: Path
    sha256: str
    size_bytes: int
    created_at: str
    uploaded_to: str | None = None
    pruned: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"file": self.path.name, "sha256": self.sha256, "size_bytes": self.size_bytes,
                "created_at": self.created_at, "uploaded_to": self.uploaded_to,
                "pruned": self.pruned or []}


def _fernet(key: str | None = None) -> Fernet:
    key = key or os.getenv("BACKUP_ENCRYPTION_KEY")
    if not key:
        raise BackupError("BACKUP_ENCRYPTION_KEY is not configured.")
    if key == os.getenv("API_KEY_ENCRYPTION_KEY"):
        raise BackupError("BACKUP_ENCRYPTION_KEY must be different from API_KEY_ENCRYPTION_KEY.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise BackupError("BACKUP_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def _integrity_ok(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise BackupError(f"SQLite integrity check failed: {result}")


def _snapshot_bytes(db_path: Path) -> bytes:
    if not db_path.exists():
        raise BackupError(f"Database not found at {db_path}.")
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "snapshot.sqlite3"
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        try:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)
        finally:
            source.close()
        _integrity_ok(snapshot)
        return snapshot.read_bytes()


def create_backup(db_path: str | Path, backup_dir: str | Path, key: str | None = None,
                  now: datetime | None = None) -> BackupResult:
    """Write one verified, encrypted backup and its manifest. Returns metadata."""
    fernet = _fernet(key)
    db_path, backup_dir = Path(db_path), Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    target = backup_dir / f"{PREFIX}{stamp}{SUFFIX}"
    if target.exists():
        raise BackupError(f"Backup {target.name} already exists.")

    token = fernet.encrypt(gzip.compress(_snapshot_bytes(db_path), compresslevel=6))
    digest = hashlib.sha256(token).hexdigest()
    partial = target.with_suffix(target.suffix + ".partial")
    partial.write_bytes(token)
    os.chmod(partial, 0o600)
    partial.replace(target)
    manifest = {"file": target.name, "sha256": digest, "size_bytes": len(token),
                "created_at": now.isoformat(), "format": "sqlite3+gzip+fernet", "schema_note":
                "Restore with scripts/restore_db.py; verify sha256 before restoring."}
    manifest_path = target.with_name(target.name + ".json")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    os.chmod(manifest_path, 0o600)
    return BackupResult(target, digest, len(token), now.isoformat())


def _backup_time(path: Path) -> datetime | None:
    name = path.name
    prefix = next((p for p in _ALL_PREFIXES if name.startswith(p)), None)
    if prefix is None or not name.endswith(SUFFIX):
        return None
    try:
        return datetime.strptime(name[len(prefix):-len(SUFFIX)], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def select_retained(paths: list[Path], keep_daily: int, keep_weekly: int, keep_monthly: int) -> set[Path]:
    """Grandfather-father-son: newest backup per day/ISO-week/month, newest first."""
    dated = sorted(((t, p) for p in paths if (t := _backup_time(p))), reverse=True)
    keep: set[Path] = set()
    for limit, bucket in ((keep_daily, lambda t: t.date()),
                          (keep_weekly, lambda t: t.isocalendar()[:2]),
                          (keep_monthly, lambda t: (t.year, t.month))):
        seen: list[Any] = []
        for moment, path in dated:
            key = bucket(moment)
            if key in seen:
                continue
            if len(seen) >= limit:
                break
            seen.append(key)
            keep.add(path)
    if dated:
        keep.add(dated[0][1])  # never delete the newest backup
    return keep


def prune_backups(backup_dir: str | Path, keep_daily: int = 7, keep_weekly: int = 4,
                  keep_monthly: int = 12) -> list[str]:
    backup_dir = Path(backup_dir)
    backups = [p for pre in _ALL_PREFIXES for p in backup_dir.glob(f"{pre}*{SUFFIX}") if _backup_time(p)]
    keep = select_retained(backups, keep_daily, keep_weekly, keep_monthly)
    removed = []
    for path in backups:
        if path not in keep:
            path.unlink(missing_ok=True)
            path.with_name(path.name + ".json").unlink(missing_ok=True)
            removed.append(path.name)
    return sorted(removed)


def _s3_client():  # pragma: no cover - exercised against real storage only
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("BACKUP_S3_ENDPOINT_URL") or None,
        region_name=os.getenv("BACKUP_S3_REGION") or None,
        aws_access_key_id=os.getenv("BACKUP_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("BACKUP_S3_SECRET_ACCESS_KEY"),
    )


def upload_backup(result: BackupResult, client: Any | None = None) -> str | None:
    """Upload backup + manifest when BACKUP_S3_BUCKET is set. Returns the object URI.

    Retention offsite is enforced by the bucket's lifecycle rules, so the upload
    credentials only need write access (no delete), which protects existing
    backups if those credentials leak.
    """
    bucket = os.getenv("BACKUP_S3_BUCKET")
    if not bucket:
        return None
    prefix = os.getenv("BACKUP_S3_PREFIX", "ramvora/").lstrip("/")
    client = client or _s3_client()
    key = f"{prefix}{result.path.name}"
    client.upload_file(str(result.path), bucket, key,
                       ExtraArgs={"ContentType": "application/octet-stream",
                                  "Metadata": {"sha256": result.sha256}})
    manifest = result.path.with_name(result.path.name + ".json")
    client.upload_file(str(manifest), bucket, key + ".json", ExtraArgs={"ContentType": "application/json"})
    return f"s3://{bucket}/{key}"


def run_backup(client: Any | None = None) -> BackupResult:
    """Backup the configured database, upload offsite if configured, then prune."""
    db_path = os.getenv("DATABASE_PATH", "data/invoice_api.db")
    backup_dir = os.getenv("BACKUP_DIR") or str(Path(db_path).parent / "backups")
    result = create_backup(db_path, backup_dir)
    result.uploaded_to = upload_backup(result, client)
    result.pruned = prune_backups(
        backup_dir,
        int(os.getenv("BACKUP_KEEP_DAILY", "7")),
        int(os.getenv("BACKUP_KEEP_WEEKLY", "4")),
        int(os.getenv("BACKUP_KEEP_MONTHLY", "12")),
    )
    _record_run(True, result.as_dict())
    logger.info("backup_complete file=%s size=%s uploaded=%s", result.path.name,
                result.size_bytes, bool(result.uploaded_to))
    return result


def _record_run(success: bool, detail: dict[str, Any]) -> None:
    from app.security import _connect
    with _connect() as conn:
        conn.execute("INSERT INTO backup_runs(created_at,success,detail) VALUES (?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), 1 if success else 0, json.dumps(detail)))


def record_failure(error: Exception) -> None:
    logger.error("backup_failed error=%s", type(error).__name__)
    try:
        _record_run(False, {"error": type(error).__name__, "message": str(error)[:300]})
    except Exception:  # pragma: no cover - never let bookkeeping mask the failure
        logger.exception("Could not record the failed backup run.")


def restore_backup(backup_file: str | Path, target_path: str | Path, key: str | None = None,
                   expected_sha256: str | None = None, force: bool = False) -> Path:
    """Decrypt, verify and install a backup at ``target_path``.

    Refuses to overwrite an existing database unless ``force`` is set; with
    ``force`` the current file is preserved as ``<name>.pre-restore-<UTC>``.
    Stop the API (or put it in maintenance) before restoring over a live file.
    """
    fernet = _fernet(key)
    backup_file, target_path = Path(backup_file), Path(target_path)
    token = backup_file.read_bytes()
    if expected_sha256 is None:
        manifest = backup_file.with_name(backup_file.name + ".json")
        if manifest.exists():
            expected_sha256 = json.loads(manifest.read_text()).get("sha256")
    if expected_sha256 and hashlib.sha256(token).hexdigest() != expected_sha256:
        raise BackupError("Backup checksum does not match its manifest; refusing to restore.")
    try:
        data = gzip.decompress(fernet.decrypt(token))
    except InvalidToken as exc:
        raise BackupError("Backup could not be decrypted: wrong key or corrupted file.") from exc

    if target_path.exists() and not force:
        raise BackupError(f"{target_path} already exists. Pass force=True (--force) to replace it.")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    staging = target_path.with_name(target_path.name + ".restore-tmp")
    staging.write_bytes(data)
    os.chmod(staging, 0o600)
    try:
        _integrity_ok(staging)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    if target_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        preserved = target_path.with_name(f"{target_path.name}.pre-restore-{stamp}")
        target_path.replace(preserved)
        # Keep the old database's WAL/SHM files with it so nothing is lost.
        for sidecar in ("-wal", "-shm"):
            old = Path(str(target_path) + sidecar)
            if old.exists():
                old.replace(Path(str(preserved) + sidecar))
    staging.replace(target_path)
    return target_path


def _main(argv: list[str] | None = None) -> int:
    """Command line: python -m app.backup {backup,restore,prune,verify} ..."""
    import argparse
    parser = argparse.ArgumentParser(prog="python -m app.backup", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup", help="Create, upload (if configured) and prune backups now.")
    restore = sub.add_parser("restore", help="Restore an encrypted backup file.")
    restore.add_argument("backup_file")
    restore.add_argument("--target", default=os.getenv("DATABASE_PATH", "data/invoice_api.db"))
    restore.add_argument("--force", action="store_true", help="Replace an existing database (old file is kept).")
    verify = sub.add_parser("verify", help="Decrypt a backup to a temporary file and run integrity checks.")
    verify.add_argument("backup_file")
    prune = sub.add_parser("prune", help="Apply the retention policy to BACKUP_DIR.")
    prune.add_argument("--dir", default=os.getenv("BACKUP_DIR"))
    args = parser.parse_args(argv)

    try:
        if args.command == "backup":
            print(json.dumps(run_backup().as_dict(), indent=2))
        elif args.command == "restore":
            print(f"Restored to {restore_backup(args.backup_file, args.target, force=args.force)}")
        elif args.command == "verify":
            with tempfile.TemporaryDirectory() as tmp:
                restored = restore_backup(args.backup_file, Path(tmp) / "verify.sqlite3")
                with sqlite3.connect(restored) as conn:
                    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                    keys = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] if "api_keys" in tables else 0
            print(json.dumps({"status": "ok", "tables": len(tables), "api_keys": keys}))
        elif args.command == "prune":
            directory = args.dir or str(Path(os.getenv("DATABASE_PATH", "data/invoice_api.db")).parent / "backups")
            print(json.dumps({"removed": prune_backups(directory)}))
    except BackupError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
