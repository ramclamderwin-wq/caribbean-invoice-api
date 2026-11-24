# SQLite backup and restore runbook — NOT YET OPERATIONAL

**Launch gate:** No offsite backup destination or scheduled backup job is configured. There is currently no Render service in the connected workspace, so there is no deployed database to snapshot. This document is a runbook, not evidence that backups exist.

## Required before accepting paid customers

1. Provision an encrypted offsite object-storage bucket in a region approved for customer data.
2. Enable bucket versioning, server-side encryption, restricted write/read access, and a lifecycle policy (proposed: daily backups retained 30 days, monthly backups retained 12 months).
3. Store backup credentials as Render secrets or use a supported workload identity. Never put credentials in Git.
4. Run a scheduled backup at least daily and after schema migrations. Alert on missing or failed backups.
5. Verify each uploaded backup with SQLite `PRAGMA integrity_check`.
6. Perform and document a restore test into an isolated staging database before launch, then at least quarterly.

## Consistent SQLite snapshot

Do not copy the live `.db` file with a plain filesystem copy while the service is running. Use SQLite's online backup API:

```python
import os
import sqlite3

source = os.environ["DATABASE_PATH"]
destination = "/tmp/quillvora-backup.sqlite3"

with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)

with sqlite3.connect(destination) as check:
    result = check.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"SQLite backup integrity check failed: {result}")
```

Upload the verified snapshot to the offsite bucket over TLS. Encrypt it at rest, restrict access, and record the object key, timestamp, and checksum. Delete the temporary local snapshot after a successful upload.

## Restore procedure

1. Put the service into maintenance mode and stop writes.
2. Download the selected backup to a secure temporary location.
3. Verify its checksum and run `PRAGMA integrity_check`.
4. Preserve the current database file separately before replacement.
5. Restore the snapshot to the configured `DATABASE_PATH`, set ownership to UID 10001, and restrict file permissions.
6. Start the service and verify `/health`, API-key authentication, usage totals, and subscription links.
7. Record the restore point, recovery duration, and any lost writes.

## Current status

- Offsite bucket: **not provisioned**
- Scheduled backup job: **not configured**
- Backup verification: **not run**
- Restore test: **not run**

Do not mark this launch gate complete until all four statuses are supported by operational evidence.
