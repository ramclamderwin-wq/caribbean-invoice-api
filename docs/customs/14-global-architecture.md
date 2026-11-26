# 14. Global architecture: one platform, modular country packs

**Goal:** add countries, languages, document types and integrations **without rebuilding
the platform**. No part of the core assumes a specific customs system. ASYCUDA, US ACE, UK
CDS, EU systems and others are optional modules.

## Layers

```
            +-------------------------------------------------------------+
 Channels   |  Web workspace  |  Public API  |  Email-in  |  Partner connectors |
            +-------------------------------------------------------------+
 Workflow   |  Upload -> Extract -> Validate -> Review -> Approve -> Export     |
            +-------------------------------------------------------------+
 Core       |  Extraction engines (rules, AI)  ->  Canonical trade document    |
            |  (commercial_invoice.v1 today; packing_list, bill_of_lading next)|
            +-------------------------------------------------------------+
 Locale     |  Languages | currencies | number/date formats | units | tax labels|
            +-------------------------------------------------------------+
 Modules    |  Country packs (rules + required fields + export formats)       |
            |  Export adapters (CSV/XLSX, ASYCUDA XML, ACE partner, CDS ...)  |
            |  Integrations (CargoWise, Magaya, Descartes, QuickBooks, Xero)  |
            +-------------------------------------------------------------+
 Platform   |  Auth, tenancy, billing, admin/audit, backups, data residency   |
            +-------------------------------------------------------------+
```

## 1. Canonical trade-document model (country-neutral)

- Every engine outputs the **same versioned schema**. `commercial_invoice.v1` is
  implemented in `app/commercial_invoice.py`, and the AI engine uses the same schema in
  `scripts/compare_engines.py`.
- **Fields are generic trade concepts:** parties, invoice identifiers, dates, currency,
  Incoterm, origin, charges, and line items.
- **Values are copied, never inferred.** Country-specific meaning (tariff codes, procedure
  codes, valuation methods) is **not** in the core.
- **Versioning:** additive changes create v1.x; breaking changes create v2, with
  converters. API clients pin a version.
- **Next document types:** packing list (weights, packages, marks), bill of lading / air
  waybill. Later, cross-document matching (invoice ↔ packing list ↔ B/L).

## 2. Extraction engines (pluggable)

```python
class ExtractionEngine(Protocol):
    name: str
    def extract(self, document: bytes, media_type: str, hints: ExtractionHints) -> TradeDocument: ...
```

- **Rules engine:** today's PDF text and OCR pipeline. Cheap; English and Spanish OCR.
- **AI engine:** multilingual document model, the path to worldwide languages.
- **Hybrid** (likely production): AI reads the document; rules validate and normalise.
- **Selection** is per tenant and per document. The language detected, the cost limit and
  the customer's data-sharing consent can each force an engine.

## 3. Locale layer (configuration, not code forks)

| Concern | Today | Global design |
|---|---|---|
| Currencies | 22 ISO codes plus €, £, BZ$ (**owner decision: keep 22 for now**) | Registry-driven list; adding codes is a config change with tests, scheduled when customers need them |
| Languages | Labels in English and Spanish; OCR `eng+spa` | Label dictionaries per language; AI engine for non-Latin scripts; extra OCR languages optional |
| Numbers | `1,234.56`, `1.234,56`, `1 234,56`, `1'234.56` | Plus locale hints per tenant/supplier |
| Dates | ISO, English and Spanish month names; ambiguous numeric dates not guessed | Month dictionaries per language; supplier-country hints to resolve DD/MM vs MM/DD **only** when the customer configures it |
| Units of measure | Copied as printed | Optional mapping to UN/ECE Rec. 20 codes in country packs |
| UI | English | i18n framework; Spanish, Portuguese and French by demand |

## 4. Country packs (the modular customs layer)

A country pack adds country-specific behaviour **on top of** the canonical document. It
never changes the core.

```python
class CountryPack(Protocol):
    country: str                      # ISO 3166-1 alpha-2, e.g. "US", "GB", "MX", "JM"
    systems: list[str]                # e.g. ["ACE"], ["CDS"], ["ASYCUDA World"]
    def required_fields(self, procedure: str) -> list[FieldRule]: ...
    def validate(self, doc: TradeDocument) -> list[Issue]: ...      # e.g. origin required per line
    def exports(self) -> list[ExportAdapter]: ...                    # formats this country accepts
```

- **Packs are data-driven where possible:** required fields and validation rules as
  versioned config files, reviewed by a person who knows that country's rules.
- **The "generic" pack is the default:** no country rules, CSV/XLSX export. Every customer
  worldwide can use RAMVORA with it from day one.
- **Prioritisation:** a pack is built only when paying customers in that country request
  it. Examples: an ACE partner-software import format for US brokers; a CDS intermediary
  format for the UK; an ASYCUDA World import format for countries that support it.
- **Classification, duties and filing remain out of scope.** A pack may later *display*
  verified tariff references as suggestions, never as automatic decisions.

## 5. Export adapters and integrations

```python
class ExportAdapter(Protocol):
    format_id: str                    # "csv.generic", "xlsx.pilot", "asycuda.xml", ...
    def render(self, docs: list[TradeDocument], mapping: ColumnMapping) -> bytes: ...
```

- **Built:** `csv.pilot` (`app/pilot_export.py`).
- **Next:** XLSX with customer column mapping. That covers most customers in any country,
  because many systems import spreadsheets.
- **Integrations** (CargoWise, Magaya, Descartes, accounting tools) are connectors behind
  the same interface. Each is built only when there is demand.

## 6. Platform services (reused from the current codebase)

- **Tenancy:** organisation → users → documents; per-tenant settings (locale hints, engine
  choice, export mappings, retention).
- **Billing:** Stripe logic already handles subscriptions, holds and idempotent webhooks.
  It needs multi-currency price display and tax handling for worldwide self-serve.
- **Security:** hashed keys, admin audit, rate limits, upload limits, encrypted backups
  (already built).
- **Data residency:** the design allows regional deployments (e.g. EU) with the same code.
  Documents and results stay in the tenant's region, and the AI provider's region is
  disclosed. This is a requirement before selling heavily into the EU.
- **Database:** move from SQLite to Postgres before multi-instance or multi-region
  operation.

## 7. What changes in the current code (incremental, not a rewrite)

| Step | Change | When |
|---|---|---|
| 1 | Keep `app/commercial_invoice.py` as the canonical model; move the AI adapter from `scripts/` into `app/` behind the `ExtractionEngine` interface | After the AI benchmark is approved |
| 2 | Add `app/country_packs/generic.py` (no rules, CSV/XLSX), with the interface above | With the pilot |
| 3 | Extract locale dictionaries (labels, months) from `app/extraction.py` into data files | When adding the next language |
| 4 | Endpoint `POST /v1/documents` (type, engine, country pack, export format), versioned | Phase 2 platform |
| 5 | Postgres and regional deployment support | When scale or the EU requires it |
