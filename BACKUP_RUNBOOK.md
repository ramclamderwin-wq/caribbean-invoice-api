# SQLite backup and restore runbook

**Status:** the backup and restore code is implemented and tested automatically
(`tests/test_backup.py`), including a real restore round trip. **Offsite backups
are not operational yet:** no storage bucket exists and no Render service has
been created. This launch gate stays open until the "Operational evidence"
checklist below is complete.

## How it works

`app/backup.py` (also runnable as `python -m app.backup ...`):

1. Takes a consistent snapshot with SQLite's online backup API. It is safe while
   the API is serving requests; never copy the live `.db` file directly.
2. Runs `PRAGMA integrity_check` on the snapshot.
3. Compresses it and encrypts it with `BACKUP_ENCRYPTION_KEY` (Fernet:
   AES-128-CBC plus HMAC-SHA256 authentication). The plaintext never touches disk
   outside a temporary directory.
4. Writes `quillvora-<UTC timestamp>.sqlite3.gz.enc` plus a `.json` manifest with
   its SHA-256 checksum to `BACKUP_DIR` (files are `0600`, the directory `0700`).
5. Uploads both files to S3-compatible storage when `BACKUP_S3_BUCKET` is set.
6. Prunes local copies, keeping the newest backup for each of the last 7 days,
   4 ISO weeks and 12 months (configurable). The newest backup is never deleted.
7. Records each run (success or failure) in the `backup_runs` table, visible at
   `GET /v1/admin/backups`.

**Why in-app scheduling:** a Render persistent disk attaches to one service only,
so a separate Render Cron Job cannot read the database. With
`BACKUP_ENABLED=true` the API starts a backup 10 minutes after startup and then
every `BACKUP_INTERVAL_HOURS` (default 24). Run one on demand with
`POST /v1/admin/backups/run` (see `ADMIN_GUIDE.md`) or `python -m app.backup backup`
in the Render shell.

### What is in a backup

The whole database:

- API keys as SHA-256 hashes, plus Fernet-encrypted copies waiting for email
  delivery;
- customer emails, Stripe customer and subscription IDs;
- usage counts and the admin audit log.

No invoice contents are stored. Because emails and Stripe IDs are personal data,
**every backup is encrypted before it is written**. `BACKUP_ENCRYPTION_KEY`
must differ from `API_KEY_ENCRYPTION_KEY`; the code refuses to run if they match.

## One-time setup (owner action: needs a storage account; costs money)

1. Create a bucket with an S3-compatible provider (for example AWS S3,
   Backblaze B2 or Cloudflare R2) in a region approved for customer data.
2. Enable bucket versioning and (if offered) object lock. Add lifecycle rules
   that keep daily backups 30 days and monthly backups 12 months.
3. Create **write-only** credentials limited to that bucket and prefix
   (`PutObject`; no delete or list). If the server is compromised, existing
   backups cannot be deleted.
4. Generate the backup key:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Save it in your password manager **and** in Render as `BACKUP_ENCRYPTION_KEY`.
   Losing it makes every backup unreadable.
5. In Render set `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY_ID`,
   `BACKUP_S3_SECRET_ACCESS_KEY`, plus `BACKUP_S3_ENDPOINT_URL` and
   `BACKUP_S3_REGION` for non-AWS providers. Then set `BACKUP_ENABLED=true` and
   redeploy.
6. Trigger `POST /v1/admin/backups/run` and confirm the object appears in the
   bucket.
7. Set up an alert: check `GET /v1/admin/backups` daily (or from monitoring) and
   alert if the newest successful run is older than 26 hours.

## Restore procedure

Practise this on staging first; the commands are the same in production.

1. **Stop writes.** In Render, suspend the service or scale it down. For a
   staging drill, restore to a separate path instead (step 4 with `--target`).
2. **Get the backup.** Download the `.enc` file and its `.json` manifest from
   the bucket (or use the local copy in `BACKUP_DIR`) into the Render shell or
   an isolated machine.
3. **Verify it** (decrypts to a temporary file and checks integrity):
   ```bash
   python -m app.backup verify /var/data/backups/quillvora-<stamp>.sqlite3.gz.enc
   ```
4. **Restore it.** The checksum is verified against the manifest
   automatically. Restoring onto an existing database requires `--force`, and
   the current file (with its `-wal`/`-shm` files) is kept as
   `invoice_api.db.pre-restore-<UTC>`:
   ```bash
   python -m app.backup restore /var/data/backups/quillvora-<stamp>.sqlite3.gz.enc \
     --target /var/data/invoice_api.db --force
   ```
5. **Start the service** and check `/health`, an API key, `/v1/usage` totals,
   and `GET /v1/admin/customers`.
6. **Reconcile with Stripe.** Changes made after the backup are lost. Resend
   any recent Stripe events from the Stripe Dashboard; the webhook handler is
   idempotent and re-reads current subscription state. Customers who signed up
   after the backup may need their key re-issued through recovery.
7. **Record** the restore point, the time taken and what was lost.

## Operational evidence (launch gate)

- [ ] Offsite bucket provisioned with versioning and lifecycle rules
- [ ] `BACKUP_ENABLED=true` on staging; scheduled run visible in `/v1/admin/backups`
- [ ] Backup object confirmed in the bucket
- [ ] Restore drill on staging from the **offsite** copy, with timing recorded
- [ ] Alert for missing or failed backups configured
- [ ] Restore drill repeated at least quarterly
