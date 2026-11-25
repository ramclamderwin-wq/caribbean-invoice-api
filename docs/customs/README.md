# Quillvora customs direction: deliverables index

Prepared 2026-11-25 for the change of initial market to **customs brokers and
importers worldwide**. The product is global from day one (owner decision); focus is on the customer type, not a country. All documents separate:

- **Fact:** verified in this repository or from a cited public source (see `SOURCES.md`);
- **Assumption:** believed but not verified, and to be tested in validation;
- **Recommendation:** proposed decision.

**No customer interviews, commitments, invoice samples or accuracy results exist yet.**
Everything below about customers is a hypothesis until the validation programme produces evidence.

| # | Deliverable | File |
|---|---|---|
| 1 | Revised product specification | [01-product-spec.md](01-product-spec.md) |
| 2 | Customs broker / importer customer profile | [02-customer-profile.md](02-customer-profile.md) |
| 3 | Global customer acquisition strategy | [03-first-market.md](03-first-market.md) |
| 4 | Competitor comparison | [04-competitors.md](04-competitors.md) |
| 5 | Technical gap analysis | [05-gap-analysis.md](05-gap-analysis.md) |
| 6 | Line-item extraction plan | [06-line-item-plan.md](06-line-item-plan.md) |
| 7 | AI extraction comparison plan | [07-ai-comparison-plan.md](07-ai-comparison-plan.md) |
| 8 | Six-week validation programme | [08-validation-programme.md](08-validation-programme.md) |
| 9 | Interview questionnaire | [09-interview-questionnaire.md](09-interview-questionnaire.md) |
| 10 | Concierge pilot design and pricing | [10-concierge-pilot.md](10-concierge-pilot.md) |
| 11 | Roadmap, costs and timelines | [11-roadmap.md](11-roadmap.md) |
| — | Commercial pricing strategy and naming | [12-pricing-and-naming.md](12-pricing-and-naming.md) |
| — | **Global market research: regions, segments, willingness to pay** | [13-global-market-research.md](13-global-market-research.md) |
| — | **Global architecture: modular country packs** | [14-global-architecture.md](14-global-architecture.md) |
| — | **Customer acquisition plan: first 3–5 paying pilots** | [15-first-pilots-plan.md](15-first-pilots-plan.md) |
| — | Prospect research list (100 companies, unverified, not contacted) | [prospecting/](prospecting/README.md) |
| — | Outreach templates (English, Spanish), drafts | [templates/](templates/) |
| — | Interview tracking and feedback process | [tracking/](tracking/README.md) |
| — | Pilot agreement and consent form, drafts for legal review | [legal/](legal/) |
| — | Synthetic demonstration | [/demo](../../demo/README.md) |
| — | Sources | [SOURCES.md](SOURCES.md) |

## Built in this round (code, all local and tested; nothing deployed)

- `app/commercial_invoice.py`: prototype line-item and commercial-invoice extraction
  (schema `commercial_invoice.v1`); never invents values or tariff codes.
- `app/pilot_export.py`: pilot spreadsheet export (`invoices.csv`, `line_items.csv`).
- `scripts/compare_engines.py`: benchmark comparing the rule engine with a Claude
  document model on identical output.

## Preparation phase (2026-11-25, owner-approved)

- AI extraction engine: `app/ai_extraction.py`, **disabled** (needs `QUILLVORA_AI_ENABLED=true` plus document-owner consent).
- Concierge pilot tool: `python -m app.pilot_run --customer NAME --input FOLDER`.
- Synthetic demo: `scripts/make_demo_invoices.py`, `demo/`.
- Gate report: `scripts/validation_gates.py`.

## Spending and deployment status

No Render service, no Stripe change, no AI API calls, no deployment, PR #12 not merged.
