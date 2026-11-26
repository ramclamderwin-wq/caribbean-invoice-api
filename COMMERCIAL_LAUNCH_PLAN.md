# Commercial launch plan: recommendations

Status 2026-11-25: recommendations only. Items marked **(owner)** need a business
decision, money, an external account or legal approval. None have been
actioned.

## Launch sequence

1. **Private staging** (Render + Stripe test mode): complete
   `RENDER_STAGING.md`, the full `STRIPE_SANDBOX_TEST_PLAN.md` (21 scenarios) and
   the backup restore drill.
2. **Closed paid beta** (10–30 invited customers, live Stripe): after legal
   approval of the Terms and Privacy Policy, offsite backups and monitoring.
3. **Public launch**: after the 200-invoice benchmark is published, the
   penetration test and the free tier.

## 1. Free tier (recommended)

- **Offer:** 100 pages a month, no card, one key per verified email.
- **Why:** developers evaluate APIs before paying, so a free tier is the main
  acquisition channel for API products.
- **Abuse controls** (needed because free keys cost OCR time):
  - email verification before the key is issued;
  - per-IP signup limit (the existing throttle helper);
  - block disposable email domains;
  - lower `REQUESTS_PER_MINUTE` for free keys;
  - free keys never get overage.
- **Implementation:** the `plan='free'` default and `DEFAULT_MONTHLY_LIMIT`
  already exist. It needs a signup endpoint that emails a verification code
  (reuse the recovery-code flow), then creates a key with a 100-page limit.
  About 1–2 days of work. **(owner: approve the offer)**

## 2. Annual billing

- Add yearly prices of 10× monthly ("2 months free"): $190, $490 and $1,490.
- **Code impact:** small. Add `STRIPE_PRICE_*_ANNUAL` environment variables and
  map them to the same plan in `_subscription_plan`. Page allowances should stay
  **monthly**. The usage window currently follows the Stripe billing period,
  which would become a year, so annual subscriptions need a monthly reset inside
  the yearly period. Needs a code change and tests.
- **(owner: create the prices in Stripe after approval)**

## 3. Overage billing

- **Current behaviour:** a request that would exceed the allowance gets HTTP
  429 (hard cap). This is safe and predictable. Keep it as the default.
- **Recommended:** opt-in overage for paid plans only, billed per 1,000 extra
  pages through a Stripe Billing Meter (for example $15 / $12 / $9 per 1,000 for
  Starter / Professional / Business, priced above the plan's per-page rate so
  upgrading is the better deal).
- **Implementation:** report billed pages to the meter from `reserve_usage`
  with an idempotency key per reservation, and only once a reservation is final
  (after successful extraction). Add a per-customer overage cap.
  **(owner: decide pricing, create the meter and price)**

## 4. Customer usage dashboard

The existing `/dashboard` shows plan, pages used and pages remaining for a key
pasted into the page. Recommended next:

- a daily usage chart and the billing-period reset date (data is already in
  `api_usage` and `current_period_end`);
- an 80% / 100% allowance email (needs a background job and email template);
- links to the Stripe customer portal and key rotation, which already exist as
  API endpoints.

## 5. API documentation and onboarding

- `/docs` (OpenAPI) is generated automatically; admin routes are hidden.
- **Add:**
  - a quickstart page (curl, Python and JavaScript examples for
    `/v1/extract-file`);
  - an explanation of `review_required`, `fields_needing_review` and
    `warnings`;
  - an error reference (401, 402, 403 hold, 413, 415, 422, 429);
  - a Postman collection and sample invoices.
- **Onboarding email after checkout:** key, quickstart link, support contact.

## 6. Customer support and recovery

- Self-service: email-code key recovery, key rotation, account deletion and
  the Stripe portal already exist.
- **Owner:**
  - a support mailbox, and a published response target (e.g. one business day);
  - a status page (e.g. a hosted uptime monitor page);
  - an internal playbook for refund and dispute holds (`ADMIN_GUIDE.md`).

## 7. Terms of Service and Privacy Policy

- `TERMS_DRAFT.md` and `PRIVACY_DRAFT.md` are drafts with placeholders.
  **(owner: lawyer review in the governing jurisdiction)**
- **Also needed for business customers:**
  - a Data Processing Agreement;
  - a sub-processor list (Render, Stripe, Resend, and the backup storage
    provider);
  - data retention statements. Invoices are processed in memory and not
    stored; account data is kept until deletion; backups are kept for up to
    12 months, which must be disclosed.
- Required before live payments.

## 8. Monitoring, alerts and incident response

Minimum before paid beta:

| Signal | How |
| --- | --- |
| Uptime | External monitor on `/health` every minute; alert after 2 failures |
| Errors | Render log alerts on `request_failed` and 5xx, or an error tracker such as Sentry (owner account) |
| Stripe webhooks | Stripe Dashboard webhook failure emails; check the endpoint's success rate weekly |
| Backups | Alert if the newest successful `GET /v1/admin/backups` run is older than 26 hours |
| Undelivered keys | Daily check of `GET /v1/admin/email-deliveries/pending` |
| Disk | Render disk usage alert at 70% |

**Incident response:** one page covering who is on call, how to suspend the
service, how to restore from backup (`BACKUP_RUNBOOK.md`), how to notify
customers, and a post-incident review template.

## 9. Dependency and software licence audit

Run 2026-11-25 with `pip-licenses` on the installed runtime dependencies:

- **Permissive (MIT, BSD, Apache-2.0, PSF, MIT-CMU):** all Python runtime
  packages, including FastAPI, Uvicorn, Starlette, Pydantic, Pillow, Stripe,
  cryptography, requests, boto3, pytesseract and python-multipart.
- **MPL-2.0:** `certifi` (file-level copyleft; fine when unmodified).
- **Needs legal review:** `pypdfium2` bundles PDFium and its third-party
  licences. The Docker build copies them into the image
  (`THIRD_PARTY_NOTICES.md`); they still need sign-off.
- **System packages:** Tesseract OCR (Apache-2.0) and its language data, plus
  Debian base packages, inside the image.
- **Vulnerabilities:** `pip-audit` reports none after upgrading requests to
  2.33.1, and now runs in CI on every push.
- **Remaining:** lock transitive dependencies with hashes (`pip-compile
  --generate-hashes`) and generate an SBOM for the Docker image.

## 10. Scalability path

- **Today:** one Render instance with SQLite on a persistent disk and one OCR job
  at a time. Good for staging and early customers.
- **Next:**
  - load-test OCR throughput on the chosen plan;
  - raise `MAX_CONCURRENT_FILE_JOBS` to match CPU cores;
  - move to managed Postgres when you need more than one instance or `api_usage`
    grows large;
  - move OCR to a job queue with async results for large PDFs.

## 11. Accuracy

The extractor is rule-based and every result is marked for human review. Do not
publish accuracy figures until the benchmark in `benchmarks/README.md` has run
on at least 200 permissioned, redacted real invoices, with field-level accuracy
reported by format, language and layout. **(owner: source the invoices and get
permission)**
