# 7. AI extraction comparison plan

## What is ready (fact)

`scripts/compare_engines.py` runs both engines on the same labelled invoices:

- **A. Rules:** current OCR + rule-based extractor (local; no per-page model fee).
- **B. Claude:** a document/vision model returning the identical `commercial_invoice.v1`
  structure through a strict JSON schema. It is instructed to copy only printed values,
  use null when absent, never infer HS codes, and list uncertain fields. Refusals,
  truncation and invalid output are recorded as errors.

Both are scored by the same code. The AI adapter has only been tested with a simulated
client; **no AI calls have been made and no money spent.**

## Metrics (as requested)

| Metric | How it is measured |
|---|---|
| Supplier, invoice number, date, currency, subtotal, tax, total accuracy | Exact match after normalisation, over labelled fields only |
| Key-field document rate | Share of invoices with supplier, number, date and total all correct |
| Line-item accuracy | Recall and precision of rows; fully correct rows; per-field accuracy for description (≥85% similarity), quantity, unit, unit price, line total, SKU, origin |
| Human correction time | (a) estimate = fixes × seconds per fix (assumption, default 15 s); (b) **measured** reviewer seconds recorded in the pilot (preferred) |
| Cost per page | Model tokens × list price per page (verify current pricing); rules engine has hosting cost only |
| Speed | Seconds per document, wall clock |

## Procedure

1. **Sample:** 50+ real commercial invoices from interviewed brokers or importers, with
   written permission. Redact bank details and personal data where possible. Mix of
   layouts, languages, scan quality and page counts. Record segment, country and quality
   per invoice.
2. **Labelling:** two people label independently for 10 invoices to check label quality,
   then one person labels the rest (about 4–8 hours in total; this is the main cost).
3. **Smoke test:** run the AI engine on 2–3 invoices first, to check the request works and
   the cost per page is as expected.
4. **Full run:** rules plus Claude. Optionally compare Claude models
   (`--model claude-sonnet-5-5`, `claude-haiku-5-5`) for cost/accuracy trade-offs; model
   choice is the owner's decision.
5. **Review timing:** in the pilot, time real corrections per engine output and add them to
   the manifest (`correction_seconds`).
6. **Decide** using the rule below and write a decision record.

## Expected cost of the benchmark (assumption-based estimate)

Assumptions: about 3,000 input tokens per page (document plus instructions) and 800–2,000
output tokens per invoice (more with long tables and model reasoning).

| Model | Est. cost per 1-page invoice | 50 invoices × 3 models |
|---|---|---|
| Claude Opus 5.5 ($4/$20 per M tokens) | about $0.03–0.05 | about $2–3 |
| Claude Sonnet 5.5 ($2/$10) | about $0.015–0.025 | about $1 |
| Claude Haiku 5.5 ($0.10/$0.50) | under $0.002 | under $0.10 |

Total: **under about US$10** including retries. The run needs the owner's approval and an
API key.

## Decision rule (proposed)

Choose the engine with the lowest **total cost per correct invoice**:

> model cost + (measured correction minutes × clerk cost per minute)

subject to:

- key-field document rate ≥ about 90% on the sample, with errors caught in review;
- no invented values found in the audit;
- model cost < 20% of the planned per-invoice price.

If no engine meets this, do not launch. Improve the engine, or reconsider the segment.

## Privacy and compliance requirements before sending documents to an AI provider

- Written permission from each document owner (pilot agreement clause).
- Use the provider's commercial API terms. Check its data retention and training-use
  policy and record it in the sub-processor list.
- Keep manifests and invoices out of Git (already documented in `benchmarks/README.md`).
