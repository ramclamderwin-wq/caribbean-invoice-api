# Staging test results (2026-11-26)

Environment: Render web service `ramvora-api-zxug` (Starter, 1 GB disk, Oregon),
branch `fix/production-readiness-p0-final`, tests 1–29 on commit `9d9d1e1`, fix re-verified on `3b9ae14`, auto-deploy off,
Blueprint "RAMVORA staging" with auto-sync off. Stripe **test mode only**
(webhook `we_1Ufud0KqMzLsvG4ZhHBKAqEX`, 12 events). Email via Resend test sender.
Synthetic demo invoices only; no real customer data. No secrets are recorded here.

| # | Test | Result |
|---|---|---|
| 1 | `/health` returns `{"status":"ok","service":"ramvora-api"}` | PASS |
| 2 | `/` shows RAMVORA name, v0.5.0, tagline | PASS |
| 3 | Security headers: HSTS, nosniff, X-Frame-Options DENY | PASS (HSTS proves HTTPS is seen behind Render's proxy) |
| 4 | `/docs` and `/dashboard` load | PASS |
| 5 | API call without a key is refused | PASS (401) |
| 6 | Webhook with invalid signature is refused | PASS (400) |
| 7 | Admin API with wrong key is refused | PASS (401) |
| 8 | Admin creates a customer key | PASS |
| 9 | Extraction from pasted text | PASS (all 7 header fields correct, `review_required` true) |
| 10 | Extraction from text PDF (demo-001) | PASS (DBT-2026-0412, USD 3,067.00) |
| 11 | OCR extraction from scanned image (demo-005) | PASS (ECE-5531, USD 1,470.00) |
| 12 | Usage counting in pages | PASS |
| 13 | Monthly limit enforced | PASS (3rd call over a limit of 2 → 429) |
| 14 | Data persists across restarts (disk) | PASS (key and usage survived several redeploys) |
| 15 | Checkout refuses to start without email configured | PASS (503, reason logged server-side only) |
| 16 | Checkout creates a test-mode Stripe session | PASS (`cs_test_…`) |
| 17 | Full signup: test card 4242 → webhook → key created → key emailed | PASS (owner received the email; no pending deliveries) |
| 18 | Customer record after signup | PASS (Starter, active, 1,000 pages, linked to Stripe) |
| 19 | Refund → automatic access hold | PASS (`charge.refunded` → `access_hold_reason=refunded`, status still mirrors Stripe) |
| 20 | Admin clears hold after review; audit log entry | PASS (`access_restored=true`, logged with actor) |
| 21 | Cancellation → access removed | PASS (`customer.subscription.deleted` → `canceled`, inactive) |
| 22 | Encrypted backup on demand | PASS (`ramvora-…sqlite3.gz.enc`, SHA-256 recorded) |
| 23 | All 5 synthetic demo invoices (EN, ES, EUR comma decimals, deliberate errors, scan) | PASS (header fields correct; 0.25–0.5 s for PDFs, 1.9 s for the OCR scan) |
| 24 | Bad inputs: empty file, fake PDF, unsupported type, empty text | PASS (400, 400, 415, 422; clear messages, nothing billed) |
| 25 | Admin routes hidden from public API docs; CORS preflight from unknown origin | PASS (no admin paths in `/openapi.json`; preflight refused, no allow-origin header) |
| 26 | Customer isolation: two keys have separate usage counters | PASS |
| 27 | Key rotation: old key stops working, new key keeps usage | PASS (old key → 401) |
| 28 | Key revocation | PASS (`revoked_at` set, key inactive) |
| 29 | Render events/logs since deploy | PASS (no failures, restarts, disk alerts, errors or tracebacks) |

## Defect found and fixed during verification
- **Arithmetic check skipped when no tax line is printed.** Common on commercial invoices
  (FOB + freight + insurance). Demo-001 showed an unexplained 25.00 (insurance) with no warning.
  Fix: the check now runs whenever subtotal and total exist (missing tax counts as zero) and
  includes insurance in the sum. Regression tests added (fail on the old code, pass on the new).
  **Redeployed to staging with owner approval** (commit `3b9ae14`, deploy live 2026-11-26 06:44 UTC).
  Verified on staging after the redeploy: the no-tax mismatch case is now flagged
  (`subtotal`, `tax`, `total` marked for review), and all 5 demo invoices still return the
  same totals with no false warnings (demo-001: 2,862 + 180 freight + 25 insurance = 3,067).

## Defect found and fixed: client address behind Render's proxies
- **Finding (independent audit, 2026-11-26):** with `TRUSTED_PROXY_HOPS=1`, the app recorded a
  different *edge proxy* address on almost every request (19 admin requests → 16 fingerprints,
  none matching the tester's real addresses). Per-IP protections were therefore ineffective on
  Render: invalid-key throttle, checkout/recovery limits, admin lockout and audit attribution.
- **Fix:** Render has two proxy layers; staging now uses `TRUSTED_PROXY_HOPS=2` and `render.yaml`
  was corrected. **Verified on staging:** fingerprints match the tester's real addresses, and a
  forged `X-Forwarded-For: 1.2.3.4` header is ignored. New unit tests pin the behaviour.
- **Per-key limit:** verified on staging (60 requests/minute; request 61 → 429; rejected uploads not billed).
- **Invalid-key throttle end-to-end:** not demonstrable from the test environment because its
  outgoing traffic rotates across ~25 addresses (each stayed under the limit of 30/minute);
  covered by unit tests plus the address verification above.

## Roadmap work (2026-11-26, later the same day)
| # | Test | Result |
|---|---|---|
| 30 | Beta `POST /v1/commercial-invoice/extract-file` on demo invoices 001/002/004/005 | PASS (schema `commercial_invoice.v1`; demo-001: seller, buyer, FOB Shenzhen, origin China, freight 180, insurance 25, 4 line items with HS codes copied as printed; demo-004: wrong line total, missing buyer and line-sum mismatch flagged, not fixed) |
| 31 | Beta endpoints require a key; listed in `/openapi.json` | PASS (401 without key) |
| 32 | Labelled supplier ("Seller: X") returned without the label | PASS after fix `27cac1f` |
| 33 | Dispute with Stripe test card 4000 0000 0000 0259 | **FAIL → fixed**: `charge.dispute.created` arrived before `checkout.session.completed`, so the hold was dropped. Fix `45a4836` remembers early refund/dispute holds and applies them when the key is created (exactly once). The pre-fix test customer was held manually by an admin (`manual_review`). End-to-end re-test needs one more dispute checkout. |

Known beta gaps on demo invoices: unit of measure is not captured; per-line origin on demo-001 is missed.

## Off-site backups (2026-11-26)
| # | Test | Result |
|---|---|---|
| 34 | Encrypted backup uploads to Cloudflare R2 (bucket `ramvora-backups-staging`, token scoped to that bucket) | PASS (`uploaded_to` set, SHA-256 recorded; no code change needed for R2) |
| 35 | Scheduled backups enabled (`BACKUP_ENABLED=true`, every 24 h) | PASS (`scheduled: true`, `offsite_configured: true`, `encryption_configured: true`) |
| 36 | Restore drill from the off-site copy into an isolated database | PASS (2026-11-26: newest R2 object `ramvora-20261126T202741215839Z` downloaded by the owner; SHA-256 matched the manifest; `python -m app.backup verify` ok; restored into a new scratch file, never over staging; `PRAGMA integrity_check` = ok, schema v2, 11 tables, all 6 customers with correct status/holds/revocation, webhook events, audit log and checkout records present, no raw keys stored). R2 lifecycle rule deletes objects after 400 days; local copies pruned 7 daily / 4 weekly / 12 monthly |

## Company email domain (2026-11-26)
| # | Test | Result |
|---|---|---|
| 37 | Resend sending domain `ramvora.io` (DKIM, SPF MX/TXT on `send`, return-path CNAME `rsend`) | PASS (status `verified`; tracking off) |
| 38 | Test email from `no-reply@ramvora.io` to a forwarded company address | SENT (Resend accepted; delivery to the company inbox to be confirmed by the owner) |
| 39 | Product sender switched to `FROM_EMAIL=RAMVORA <no-reply@ramvora.io>` | DONE (staging redeployed; key emails can now reach any customer address) |

## Stripe lifecycle re-tests (2026-11-26, evening)
| # | Test | Result |
|---|---|---|
| 40 | Dispute re-test after fix `45a4836` (card 0259) | PASS: `charge.dispute.created` again arrived before `checkout.session.completed`; outcome `pending_hold_applied:disputed`; new customer created already held (`access_hold_reason=disputed`, inactive) |
| 41 | Failed renewal (card 0341 set as the subscription's payment method) | SCHEDULED: forcing an immediate renewal via the API produced only a $0 proration invoice (flexible billing mode). The real renewal on 2026-12-26 will fail naturally; a check is scheduled for 2026-12-27 (grace period, past_due status, recovery). Covered by unit tests meanwhile. |

**Admin IP allowlist:** not set. The owner's current address is a mobile-carrier IP that changes,
so an allowlist would risk lockouts. Recommended: a fixed office IP or a VPN with a static exit IP
(or keep the 32+ character admin key, lockout and audit log as the protection until then).

## Limits of what staging can show
- Line-item extraction is now available as a **beta** endpoint (tests 30-31); accuracy on real invoices is unmeasured.
- Backup **restore** was not run on staging: it needs shell access to the server (not available
  through the tools used), and no off-site copy exists yet. Restore is covered by automated tests.

## Not yet tested on staging
- Failed renewal / past-due grace (needs a Stripe test clock). Covered by unit tests.
- `ADMIN_ALLOWED_IPS` not set yet (admin API is key-protected and rate-limited).
