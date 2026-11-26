# 11. Development roadmap, costs and timelines

All costs are **estimates** in USD. "Dev weeks" assumes one experienced developer; with an
AI coding assistant, calendar time may be shorter, but plan conservatively. **Each phase
starts only when the previous phase's gate is met.** No large platform build before
demand is proven.

## Phase 0: Validation (weeks 1–6) ← now

| Work | Cost |
|---|---|
| 15+ interviews, 50+ invoices, labelling (founder time) | Time |
| AI benchmark run (after approval) | about $10 |
| Optional interviewee incentives / travel | $0–500 |
| Legal template review (pilot agreement, consent) | To be quoted; estimate $300–1,500 |
| Hosting | **$0** (local only) |

**Gate:** the validation targets in `08-validation-programme.md`.

## Phase 1: Concierge pilot (weeks 7–11)

| Work | Effort | Cost |
|---|---|---|
| Production-ready extraction for pilot (chosen engine, XLSX export, correction log) | 1–2 dev weeks | — |
| Secure intake (dedicated mailbox/folder per customer) | Days | $0–20/month |
| AI processing for ~450–750 invoices (3–5 customers) | — | about $10–40 (assumption: $0.02–0.05 per page) |
| Staging hosting (Render Blueprint, **only after explicit approval**) | — | about $7.25/month (owner's estimate) |
| Manual correction time (team) | Measured | Time |

**Expected revenue:** 3–5 × $249 = $750–1,250.

**Gate:** ≥3 paying pilots, ≥2 convert, time saved ≥50%, unit economics positive.

## Phase 2: Minimum platform (months 3–5)

| Work | Effort |
|---|---|
| Document storage with isolation, retention and deletion; Postgres decision | 1–2 dev weeks |
| Review UI: upload, document viewer, editable header/line table, issues, approve, export | 3–5 dev weeks |
| Workspaces, users and roles; invite flow | 1–2 dev weeks |
| Platform billing plans (reuse Stripe logic; test mode first, with approval) | 3–5 days |
| Accuracy and time-saved dashboard from correction logs | 1 week |
| Global foundations: engine interface, generic country pack, export adapters with column mapping, i18n-ready UI, tenant locale settings | 1–2 dev weeks |
| Worldwide self-serve billing: multi-currency price display, tax handling (owner approval) | 3–5 days |
| Security review, penetration test, privacy/DPA, sub-processor list | 1 week + external test ($2,000–8,000 estimate) |

- **Total:** about 10–14 dev weeks.
- **Running cost** at early scale (assumption): hosting $25–100/month; storage and
  backups $5–20/month; AI about $0.02–0.05 per page; email service $0–20/month.

**Gate:** about 10 paying customers; churn under about 5% a month; gross margin over
about 70%.

## Phase 3: Integrations and expansion (months 6–12)

| Work | Effort |
|---|---|
| Per-country declaration export formats, prioritised by customer demand (e.g. ASYCUDA World, US and UK filing-software partners); requires specs | 1–3 weeks per format |
| Packing list and bill of lading extraction; cross-document checks | 2–3 weeks |
| Email-in ingestion | 1 week |
| Localised website and UI (Spanish, Portuguese, French first, by demand); multi-currency pricing display | 2–4 weeks |
| Partner API program (forwarders, broker software vendors) | Ongoing |
| Research track: HS classification *suggestions* from verified tariff data, with legal review | Research; separate decision |

## Timeline summary

```
Weeks 1-6    Validation            ->  go / pivot / stop
Weeks 7-11   Concierge pilot       ->  convert to paid?
Months 3-5   Minimum platform      ->  ~10 paying customers?
Months 6-12  Integrations + scale marketing in best-converting countries
```

## Cost summary to the end of Phase 1 (estimate)

About **$350–2,100** in cash (mostly the optional legal review and incentives), plus
founder time. Pilot revenue may offset $750–1,250 of it.

## Biggest risks and mitigations

| Risk | Mitigation |
|---|---|
| Brokers' main pain is not keying | Interviews test this explicitly; pivot within customs if so |
| Extraction accuracy too low on real invoices | Benchmark before pilot; hybrid engine; review step catches errors |
| Competitors already serve the segment | Interview question D; differentiate on self-serve, price, multilingual invoices and review-first trust |
| Spreading too thin across countries | Same product everywhere; focus marketing where conversion is best; add country formats only on demand |
| Language coverage for worldwide invoices | AI engine (multilingual) as primary; rules as validation; add OCR languages as needed |
| Privacy law differences (GDPR etc.) | DPA, sub-processor list, deletion policy; consider EU data residency before an EU sales push |
| Data confidentiality concerns | Pilot agreement, deletion policy, sub-processor transparency |
