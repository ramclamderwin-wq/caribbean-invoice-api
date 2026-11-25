# Commercial pricing strategy and naming

## What customers pay today for comparable things (facts; see `SOURCES.md`)

| Reference point | Price |
|---|---|
| Broker fee charged to importers | US: commonly $100–250 per entry (vendor source); Jamaica: one carrier's brokerage package US$242 per bill of lading; Saint Lucia statutory minimum 200 (local currency) per entry |
| Accounting capture tools | Dext about $24–31.50/month for 250 documents and 5 users; AutoEntry about £0.32–0.48 per document (2 credits for line items); Hubdoc about $12/month |
| Generic extraction APIs | Affinda about $0.05–0.20 per page; Nanonets about $0.36–1.50 per invoice (estimates) |
| Customs/broker software | Tai Software Growth $995/month; AEB from about $3,171/month; most customs-AI tools quote on request |

## Recommended pricing model (hypothesis to test)

The unit is **the invoice, not the page.** Brokers think per entry and per invoice. Long
invoices are capped at 10 pages each, with extra pages billed as additional invoices.

**Why not the old $19/$49/$149 API plans:** those priced generic page extraction for
developers. Broker value is per invoice saved from manual keying, and line items plus
customs checks justify a higher price than accounting capture tools.

| Plan | Monthly price | Included invoices | Users | Overage | Includes |
|---|---|---|---|---|---|
| Pilot | $249 one-off, 4 weeks | up to 150 | — | — | Concierge checking |
| **Starter** | **$149** | 100 | 2 | $1.50/invoice | Extraction, review, CSV/XLSX export |
| **Professional** | **$399** | 400 | 5 | $1.10/invoice | + custom export templates, priority support |
| **Business** | **$899** | 1,200 | 15 | $0.85/invoice | + API access, per-country export format (when available), onboarding |
| Enterprise | Custom | Custom | Unlimited | Custom | Integrations (broker systems), SSO, DPA, SLA |

- **Annual billing:** 2 months free.
- **Add-ons later:** packing-list cross-checks, email-in, additional export formats.

**Why these numbers (assumptions):**

- At ~$1–1.50 per invoice the product costs well under the assumed labour cost of keying
  ($1–7.50+ per invoice) and is tiny next to the $100–250 per-entry fee.
- AI cost of ~$0.02–0.05 per page keeps model cost under 5–10% of revenue, inside the 20%
  gate.
- Plans sit between accounting capture tools (too cheap and not customs-specific) and
  broker software suites (enterprise-priced).

**Test it:** use interview question 22 (price reaction) and the pilot conversion rate.
Revise before configuring anything in Stripe. Plans are created in Stripe **test mode
only, after explicit approval.**

## Naming and repository strategy

- **Company and brand: keep "Quillvora".** It is neutral and international, which fits
  the worldwide strategy.
- **Product line:**
  - "Quillvora for Customs" or "Quillvora Trade Documents" for the broker/importer
    workspace;
  - "Quillvora API" for the engine sold to partners.
- **Public wording:** describe the product by function ("commercial invoices to
  structured customs data"), list supported currencies and languages, and avoid
  country-specific framing. Customer examples from any country can appear as case
  studies; none defines the market.
- **Repository (recommendation, needs owner approval; not done):** the current name
  `caribbean-invoice-api` contradicts the worldwide positioning, so it should be renamed.
  - Rename `caribbean-invoice-api` to `quillvora-engine` (or `quillvora-api`) after
    PR #12 is resolved. GitHub keeps redirects from the old name, but update CI badges,
    Render settings and any links.
  - Create the review workspace as a separate app (e.g. `quillvora-workspace`) that calls
    the engine API, once Phase 2 is approved.
  - Don't rename now: it touches deployment configuration and is best done in one
    planned step.
- **Code-level wording:** the code is already Quillvora-branded. `render.yaml` and the
  README are neutral, except for one historical legal-entity mention in the README.
