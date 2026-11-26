# Memo to legal reviewer: RAMVORA legal pack (draft v2)

> Prepared 2026-11-26 to brief a qualified lawyer. Not legal advice. All factual statements about the
> product were checked against the running staging service.

## 1. The business in one paragraph
Divine Group Holdings LLC (Wyoming) plans to sell **RAMVORA**, a subscription API (and dashboard)
that extracts data from invoices and commercial invoices for **businesses worldwide**. The first
target customers are customs brokers, freight forwarders and importers. Prices: US$19, US$49 or
US$149 per month for 1,000, 5,000 or 20,000 pages, paid by card through Stripe. Uploaded documents
are processed in memory and not stored. Results are always marked as needing human review. RAMVORA
does **not** classify goods, compute duties or file declarations. "RAMVORA" is a trade name: the DBA
filing and trademark clearance are still pending.

## 2. Documents in this pack
| Document | Purpose | Status |
|---|---|---|
| Terms of Service | Online subscription terms (B2B) | Draft v2 |
| Privacy Policy | Public privacy notice | Draft v2 |
| Data Processing Addendum (with sub-processor list and security annex) | For customers who need GDPR-style terms | Draft v1 |
| Acceptable Use Policy | Incorporated into the Terms | Draft v1 |
| Pilot Services Agreement | Short paid pilots with first customers | Draft v1 |
| Invoice Consent Form | Permission to use a customer's invoices to measure accuracy | Draft v1 |

## 3. Decisions we need from you (please mark up)

1. **B2B-only:** is the "business use only" approach effective in the US, EU/UK, Latin America and
   the Caribbean? Should checkout require a "business use" confirmation?
2. **Governing law and disputes:** Wyoming law. Courts or arbitration (and which rules and seat)? Is a
   small-claims carve-out advisable?
3. **Liability cap:** proposed at 12 months' fees. What carve-outs (confidentiality, data protection,
   indemnities)?
4. **Indemnities:** customer indemnity for unauthorised data. Should RAMVORA offer an IP indemnity?
5. **Refund policy:** the owner's preference is [TBD]. Also: how to present the automatic "pause
   access on refund/chargeback pending review" rule.
6. **Taxes:** Stripe Tax is off. Do we need to collect US sales tax (SaaS taxability varies by state),
   EU/UK VAT on B2B digital services (reverse charge), or others before selling internationally?
7. **Privacy roles:** confirm RAMVORA is a processor for uploaded documents and a controller for
   account data. Do we need an EU/UK representative (GDPR Art. 27) before accepting EU/UK customers?
8. **International transfers:** SCCs and UK Addendum, or reliance on providers' frameworks?
9. **Retention:** backups are kept up to 400 days off-site (deleted accounts can persist in backups
   that long). Admin audit logs are currently kept indefinitely. Recommend periods.
10. **Sanctions and export:** with worldwide B2B customers, what screening (e.g. OFAC) and
    restricted-country terms should be added?
11. **Customs disclaimers:** is section 1.3 (no classification, duty calculation, origin, valuation
    or filing) enough to avoid being treated as a customs broker or giving regulated advice in key
    countries?
12. **AI provider:** an optional AI engine (Anthropic) is built but disabled. What notice and
    consent are needed before enabling it per customer?
13. **Trade name:** wording until the RAMVORA DBA is registered ("doing business as RAMVORA (trade
    name subject to registration)").
14. **Breach notification:** the DPA proposes [48/72] hours. Confirm.

## 4. Facts you can rely on (verified 2026-11-26)

- Hosting: Render (USA, Oregon). Payments: Stripe. Email: Resend (from @ramvora.io). DNS, email
  forwarding and encrypted backups: Cloudflare (R2).
- Uploaded files: in memory only. Logs hold request metadata, not contents or secrets.
- API keys stored as hashes. Backups encrypted before upload; a restore test passed.
- Account deletion endpoint cancels subscriptions and deletes application records.
- Refunds and chargebacks automatically pause access pending manual review, including when Stripe
  reports them before signup completes.
- Usage counted per page, reset monthly (UTC). Requests over the allowance are refused (no
  overage billing).

## 5. Out of scope / not yet done
Trademark search, DBA filing, insurance (E&O / cyber), entity tax registrations, and accessibility
of the website.
