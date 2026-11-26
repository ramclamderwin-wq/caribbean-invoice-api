# Staging test results (2026-11-26)

Environment: Render web service `ramvora-api-zxug` (Starter, 1 GB disk, Oregon),
branch `fix/production-readiness-p0-final`, commit `9d9d1e1`, auto-deploy off,
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

## Not yet tested on staging
- Dispute hold (needs a checkout with Stripe dispute test card 4000 0000 0000 0259).
- Failed renewal / past-due grace (needs a Stripe test clock). Covered by unit tests.
- Off-site backup upload and a restore drill from the off-site copy (no bucket yet).
- `ADMIN_ALLOWED_IPS` not set yet (admin API is key-protected and rate-limited).
- Sending email to addresses other than the Resend account owner (needs a verified domain).
