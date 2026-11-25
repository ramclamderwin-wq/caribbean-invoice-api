# 5. Technical gap analysis

Based on a review of branch `fix/production-readiness-p0-final` (PR #12, draft, not merged)
on 2026-11-25. **Facts** are from the code; effort figures are **estimates**.

## Reuse as-is (working, tested)

| Component | Where | Notes |
|---|---|---|
| PDF text extraction + OCR fallback (eng+spa) with page/pixel/time limits | `app/main.py` (`_extract_pdf`, `_process_file`, `_ocr_image`) | Safe upload handling; malformed/fuzzed files tested |
| Header extraction (supplier, number, date, currency, subtotal, tax, discount, shipping, total, credit notes) | `app/extraction.py` | Rule-based; synthetic tests only |
| API authentication (hashed keys), per-page metering, quota reservation and release | `app/security.py`, `app/main.py` | Reusable for platform usage limits |
| Stripe billing, webhooks, holds, idempotency, lifecycle | `app/billing.py`, `app/security.py` | Needs new prices/plans for the new product; logic reusable |
| Admin API + audit log | `app/admin.py` | Extend with workspace/document views |
| Encrypted backups, restore, retention | `app/backup.py` | Becomes more important once documents are stored |
| Security hardening (proxy IP, body limits, throttles, error hygiene) | `app/net.py`, `app/main.py` | `SECURITY_REVIEW.md` |
| CI: tests, dependency audit, bandit, Docker build, smoke test | `.github/workflows/tests.yml` | |
| Benchmark runner (header fields via HTTP API) | `scripts/benchmark_invoices.py` | Normalisation reused by the new comparison |

## Built in this round (prototype, local only)

| Component | Where | Status |
|---|---|---|
| Commercial-invoice schema + line-item extraction (rules) | `app/commercial_invoice.py` | Prototype; synthetic tests; **not exposed as an endpoint** |
| Pilot spreadsheet export | `app/pilot_export.py` | CSV for Excel; formula-injection safe |
| Engine comparison (rules vs Claude) with line-item scoring, cost, speed and correction time | `scripts/compare_engines.py` | AI adapter tested with a fake client only |

## Gaps (to build only after validation evidence)

| Gap | Why needed | Est. effort | Priority |
|---|---|---|---|
| Production line-item engine (AI vision primary + rule validation) | Rules on text lines will miss complex tables (assumption to measure) | 1–2 weeks after benchmark | P1 |
| `POST /v1/extract-commercial-invoice` endpoint | API access for pilot automation and partners | 1–2 days | P1 |
| Document storage with per-customer isolation, retention and deletion | Review workspace needs stored files and results | 1–2 weeks | P1 (platform) |
| Review UI (side-by-side document + editable table, approve, export) | The core product for non-developers | 3–5 weeks | P1 (platform) |
| Multi-user workspaces (users, roles, invitations) | Broker firms have several clerks; per-user pricing | 1–2 weeks | P2 |
| Correction logging, accuracy dashboard | Measures accuracy and time saved; enables honest claims | 1 week | P1 |
| XLSX export with templates per customer | Pilot customers' own column layouts | 2–4 days | P1 |
| Per-country export formats (e.g. ASYCUDA World import where available) | Removes re-keying entirely | 1–3 weeks per country + spec access | P2 |
| Packing list / bill of lading extraction and cross-checks | Weights, packages, consignee consistency | 2–3 weeks | P3 |
| Email-in ingestion | How brokers actually receive documents (assumption) | 1 week | P3 |
| **Global:** full ISO 4217 currency recognition (today about 22 codes, mostly Americas/Europe) | Worldwide invoices | 2–3 days (careful: some codes are ordinary words) | P1 |
| **Global:** multilingual extraction (today OCR is English and Spanish only) | Asian, European and other supplier invoices | Via AI engine; or more Tesseract languages (bigger image) | P1 |
| **Global:** locale-aware numbers/dates and unit-of-measure normalisation | Worldwide formats | 1 week | P1 |
| **Global:** privacy/compliance (GDPR DPA, sub-processors, possible EU data residency) | Selling in the EU/UK and elsewhere | Legal + 1 week engineering | P1 before EU sales |
| **Global:** multi-currency price display, tax/VAT on subscriptions | Worldwide self-serve billing | 3–5 days + owner approval | P2 |
| HS classification *suggestions* from verified tariff data | High value but legal risk; research track | Research | Later |
| Database move from SQLite to Postgres | Multi-instance scale, document metadata volume | 1–2 weeks | When scale requires |
| Billing plans for platform (per-invoice tiers, users, overage) | New pricing model | 3–5 days (logic exists) | After pricing validated |

## Things that must not be done

- Do not rewrite the extraction pipeline, billing or security layers; extend them.
- Do not expose tariff classification or duty calculation as automatic outputs.
- Do not store customer invoices before retention, deletion and isolation are designed.

## Repository and naming impact

See `12-pricing-and-naming.md`. Keep this repository as the engine; add the platform as a
separate app or package once the review UI is approved.
