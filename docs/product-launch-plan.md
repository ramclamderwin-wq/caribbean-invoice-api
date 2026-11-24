# Product launch plan

## Objective

Turn the existing invoice extraction API into a reliable, paid B2B component that software vendors and accounting/workflow platforms can embed. The first commercial proof is a small number of design partners and paying pilot customers, not a premature attempt to reach 1,000 customers.

## What exists today

Verified from the current repository:
- FastAPI service with text extraction, PDF/image upload, OCR via Tesseract, API-key authentication, monthly usage counting, and Stripe Checkout/Customer Portal/webhook code.
- Deterministic rule-based extraction of supplier, invoice number, date, currency, subtotal, tax, and total.
- Results explicitly require human review; confidence values are presence indicators, not calibrated probabilities.
- A test suite covering extraction variations, API endpoints, PDF upload, and mocked image OCR.

Not yet demonstrated:
- Accuracy on representative real-world invoices across industries, countries, languages, layouts, and scan quality.
- Production deployment and a complete live-like Stripe Sandbox customer journey.
- Safe recovery/rotation if a customer loses their one-time API key.
- Reliable behavior under concurrent requests and quota-boundary conditions.
- Customer support, privacy/retention controls, operational monitoring, backups, and a documented incident process.
- Commercial demand or willingness to pay.

## Initial customer profile

Start with small-to-mid-sized vertical SaaS vendors that already manage vendor bills, job costs, procurement, field service, or expense workflows and want invoice extraction embedded in their product.

Do not assume a target vendor has a gap. First qualify the workflow and integration fit. BuildOps is a research candidate, not a confirmed prospect or customer. Other candidate segments include field-service platforms, construction procurement software, facilities-management platforms, and bookkeeping software providers.

## Positioning to test

"An embeddable invoice data extraction API that turns PDF and image invoices into structured, reviewable data, with clear warnings and a human-in-the-loop design."

Do not claim autonomous accounting, guaranteed accuracy, fraud detection, duplicate detection, line-item extraction, or learned categorization until those capabilities are implemented and validated.

## Phase 1 — make the current product safe to pilot

1. Run the full CI suite on the current main branch and preserve the result.
2. Review API authentication, admin-key handling, rate limits, upload limits, PDF/image parsing, and database behavior.
3. Add tests for quota boundaries, concurrent requests, invalid/oversized files, subscription status changes, duplicate webhook delivery, and checkout-claim retry behavior.
4. Fix critical correctness and security findings before exposing a public endpoint.
5. Configure Stripe in Sandbox only; test checkout, payment confirmation, key issuance, usage, portal, cancellation, and failed-payment behavior.
6. Do not enable live payments until the Sandbox journey passes and business/legal readiness is reviewed.

## Phase 2 — measure extraction quality

Create a permissioned benchmark of at least 100 invoices from multiple vendors and layouts. Redact personal and bank details where possible. Maintain a human-verified expected result for each target field.

Measure field-level exact match and normalized numeric/date match separately for:
- supplier name
- invoice number
- invoice date
- currency
- subtotal
- tax
- total

Report OCR and text-PDF results separately. Track false extraction, missing fields, and incorrect currency/decimal interpretation. Keep all outputs review-required until evidence supports a safer policy.

## Phase 3 — prove demand before expanding scope

Conduct 15 structured discovery conversations with product managers, engineering leads, and operations/accounting leads at relevant software vendors. Ask about invoice volume, current workflow, failure rates, existing vendor/tool, integration requirements, security review, budget owner, and purchasing timeline.

Offer a narrow paid pilot only after Phase 1 and Phase 2 gates pass. A pilot should specify document volume, supported formats, success measures, human review expectations, data retention, support, and price.

## Phase 4 — build only what pilots demand

Potential roadmap, ordered by evidence:
1. Customer-level API key rotation and secure recovery workflow.
2. Better structured error responses, request IDs, idempotency, and usage reporting.
3. Line-item extraction and tax/discount/shipping handling.
4. Duplicate detection and customer-specific categorization rules.
5. Accounting/procurement integrations requested by pilot customers.
6. Optional AI extraction provider behind a configurable interface, with privacy controls and measurable accuracy/cost comparisons.

## Commercial validation metrics

Do not scale based on signups alone. Track:
- benchmark field accuracy and review rate
- successful requests / total requests
- median and 95th percentile latency
- cost per processed page and invoice
- gross margin per plan and per customer
- pilot-to-paid conversion
- active customers and monthly retention
- support time per customer

A price is viable only if processing, infrastructure, payment fees, support, and sales costs leave an acceptable gross margin.

## Launch gates

A public paid launch requires all of the following:
- repeatable test suite passing
- real-invoice benchmark results documented
- no unresolved critical/high security findings
- Sandbox billing lifecycle fully verified
- production secrets, webhook, backups, monitoring, and restore procedure configured
- privacy policy, terms, data processing/retention policy, and support contact reviewed
- company tax, registration, and payment obligations reviewed by qualified professionals

## Guardrails

- Keep the existing brand provisional until trademark/domain clearance is completed.
- Do not commit credentials, customer invoices, or personal data.
- Do not incur paid infrastructure, advertising, domain, legal, or vendor costs without explicit approval.
- Do not claim a feature, integration, accuracy level, customer, or deployment is live unless verified.
