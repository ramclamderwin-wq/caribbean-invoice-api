# 3. Go-to-market: global from day one

**Owner decision (2026-11-25):** Quillvora is built and sold worldwide from the start. It is
not a regional product. This replaces the earlier recommendation to validate in a single
Caribbean country.

## Strategy (recommendation)

**Focus on one customer type, everywhere. Don't focus on a country.**

- **Who:** independent customs brokers and small-to-mid importers that process supplier
  commercial invoices, in any country.
- **How they find us:**
  - online, self-serve: website, free trial, transparent pricing in USD;
  - searchable content ("commercial invoice to Excel", "extract invoice line items for
    customs");
  - LinkedIn;
  - broker and forwarder directories and associations;
  - software-partner integrations later.
- **What stays global in the product:**
  - any currency (ISO 4217);
  - multilingual invoices;
  - any number and date format;
  - generic CSV/Excel export with column mapping;
  - country-specific declaration formats added later, by demand, not upfront.

## Why customer-type focus instead of a single country

- Validation needs a **comparable group**. Fifteen interviews with the same kind of
  business in five countries still teach a lot. Fifteen interviews spread across brokers,
  accountants and retailers do not.
- Online acquisition doesn't depend on geography. The same message and offer can reach
  brokers anywhere.
- It avoids building the product around one customs system.

## Where the first customers will likely come from (facts and assumptions)

| Market group | Facts | Implication |
|---|---|---|
| **English-speaking high-import markets** (US, UK, Canada, Australia, Ireland, NZ) | US alone: about 11,000–14,000+ licensed brokers (CBP / trade.gov). Funded AI entry tools already compete there | Biggest demand and willingness to pay, but most competition. Win on self-serve, price, speed to value, review-first trust |
| **ASYCUDA countries** (about 102 countries and territories: Caribbean, Africa, Asia-Pacific, Latin America) | UNCTAD | Fewer specialised tools (assumption); one data format may be reusable across many countries |
| **Spanish/Portuguese-speaking markets** (Latin America, Spain) | Engine already reads Spanish; AI engine covers more languages | Localised website and support later |
| **EU** | Multilingual invoices, strict privacy rules (GDPR) | Needs a DPA, data-processing terms and possibly EU data residency before selling |

## Validation approach (updated)

- 15+ interviews with independent customs brokers and importers in **at least 3
  countries**, recruited online and through the founder's network. Track country in every
  row so differences show up.
- Pilot customers can be anywhere. The concierge pilot works by email and spreadsheet.
- If one country or language clearly converts better, put the marketing there. The
  product stays global.

## Honest constraints

- **Language coverage:**
  - the current rule engine reads English and Spanish only (Tesseract `eng+spa`);
  - worldwide invoices (Chinese, French, German, Portuguese, Arabic and more) will need
    either the AI engine or additional OCR languages;
  - so the AI comparison is now more important.
- **Privacy law** differs by country (GDPR in the EU/UK, and others). A clear privacy
  policy, DPA and sub-processor list are needed before taking documents from those
  regions.
- **Time zones and support:** self-serve onboarding and written documentation matter more
  than live support.
- **Competition is strongest in the US.** Expect a lower conversion rate there, and test
  messaging.
