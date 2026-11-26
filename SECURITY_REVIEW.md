# Security and reliability review — 2026-11-25

Scope: the code on branch `fix/production-readiness-p0-final`. This is an
internal code review with automated tests, not an independent penetration
test. Commission one before open public launch.

## Fixed in this review

| # | Finding | Risk | Fix | Test |
| --- | --- | --- | --- | --- |
| 1 | Per-IP limits (checkout, recovery, admin) read the left-most `X-Forwarded-For` entry, which the client controls, because Uvicorn trusts all proxies. | Rate limits and allowlists bypassable with a forged header | `app/net.py` uses the proxy-appended entry (`TRUSTED_PROXY_HOPS`, Render = 2; see item 4 below) | `test_admin.py` forged-header tests |
| 2 | A renewal or subscription update re-enabled a key the customer had **revoked**. | Leaked or retired key silently works again | Separate `revoked_at`; no Stripe event can clear it | `test_revoked_key_is_never_reactivated_by_stripe` |
| 3 | Refund/dispute holds were stored in `subscription_status`, and an earlier fix kept that value even after Stripe cancelled. | Wrong status shown to support; hold logic tangled with billing | Separate `access_hold_reason`; status mirrors Stripe | `test_lifecycle.py` |
| 4 | Refund/dispute webhooks acted before deduplication; redelivered or delayed events could re-suspend after a manual review. | Wrongful suspension of paying customers | Atomic dedupe plus a review cutoff | `test_hold_events_are_idempotent_and_respect_manual_review` |
| 5 | Admin key had no minimum length, no lockout and no audit trail; admin route visible in `/docs`. | Brute force; no accountability | 32-character minimum, failure lockout, IP allowlist, audit log, hidden from docs | `test_admin.py` |
| 6 | Public 503 errors exposed configuration details (e.g. "API_KEY_ENCRYPTION_KEY must be a valid Fernet key"). | Information disclosure | Generic customer message; detail logged for operators | `test_public_errors_do_not_reveal_configuration` |
| 7 | JSON endpoints had no body-size cap (only uploads and webhooks did). | Memory exhaustion | `MAX_JSON_BODY_BYTES` (1 MiB) applied to every other path | `test_json_endpoints_reject_oversized_bodies` |
| 8 | Unlimited invalid API-key attempts. | Database load from key guessing | Per-IP throttle (`INVALID_KEY_RATE_LIMIT`, 30/min) | `test_invalid_api_key_guessing_is_throttled` |
| 9 | `api_request_events` gained a row on every call and was never pruned. | Unbounded database growth | Rows older than one hour pruned on each write | `test_request_event_log_is_pruned` |
| 10 | `requests` 2.32.5 had a published advisory (PYSEC-2026-2275). | Known vulnerability | Upgraded to 2.33.1; `pip-audit` added to CI | CI step |
| 11 | Past-due grace check crashed on a timestamp without a timezone. | 500 error for affected customers | Normalised to UTC | lifecycle grace test |
| 12 | Tests shared `data/invoice_api.db`, so leftover rate-limit rows from earlier runs made later runs fail. | Flaky verification | Each test gets its own database | full suite repeated 3 times |

## Verified (no change needed)

- **API keys:** 256-bit random, stored as SHA-256 hashes. A Fernet-encrypted
  copy is kept only until email delivery succeeds.
- **Stripe webhooks:** signature checked through `StripeClient.construct_event`
  and body size limited. Subscription state is re-read from Stripe, events are
  deduplicated by ID, and older events are ignored.
- **Uploads:** extension allowlist, byte limit enforced before multipart
  parsing, PDF page limit, OCR page limit, pixel limits (including
  decompression bombs) and OCR timeout. Page quota is reserved before OCR and
  released on any failure. 28 malformed and fuzzed files produced no 500 errors
  and no incorrect charges (`test_hardening.py`).
- **Logging:** the request log records the method, path, status and duration
  only; no query strings, keys, emails or invoice text. Admin audit entries store
  a salted hash of the client IP, not the IP itself.
- **HTTPS:** behind the proxy (`X-Forwarded-Proto: https`) the app sends HSTS,
  `nosniff`, `X-Frame-Options: DENY` and a referrer policy. Checked by running
  Uvicorn with the production flags.
- **Errors:** unexpected failures return a generic 500 with no stack trace.
  Customer-facing messages contain no internal paths.
- **Static analysis (bandit):** no high-severity findings. The 14
  medium/low-confidence "SQL built from strings" warnings were each reviewed:
  only fixed column lists, fixed `WHERE` fragments or `?` placeholders are
  inserted, and all user input is bound as parameters. The two `urlopen`
  warnings use a hardcoded `https://api.resend.com` URL.

## Remaining risks and recommendations

1. **Single SQLite file, single process.** Correct for staging and early
   customers. Plan a move to managed Postgres before horizontal scaling or high
   volume: `api_usage` stores one row per billed page.
2. **OCR throughput:** `MAX_CONCURRENT_FILE_JOBS=1` by default. Load-test on the
   chosen Render plan before launch and size it accordingly.
3. **Admin authentication is one shared key.** Fine for a single operator.
   Before adding staff, move to per-person credentials (SSO or individual keys)
   so the audit actor is authenticated, not self-declared.
4. **`TRUSTED_PROXY_HOPS` must match the real network path.** On Render it is
   **2**, not 1. Verified on staging (2026-11-26) by comparing admin-audit client
   fingerprints with the tester's known addresses: with 1, every request got a
   different edge address, which silently disabled per-IP limits (invalid-key
   throttle, checkout/recovery limits, admin lockout); with 2, the real client
   address is used and a forged `X-Forwarded-For` is ignored. Re-check whenever a
   CDN or another proxy is added in front.
5. **Dependency pinning:** direct dependencies are pinned and audited in CI.
   Transitive dependencies are not locked yet; consider `pip-compile` with
   hashes.
6. **Independent penetration test** before open signup.
