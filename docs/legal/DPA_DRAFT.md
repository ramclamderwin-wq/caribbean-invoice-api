# RAMVORA Data Processing Addendum: DRAFT FOR LEGAL REVIEW

> **Draft v1 (2026-11-26). Not legal advice. Not for signature.** Based on the deployed service.
> Counsel should align it with GDPR Art. 28, UK GDPR, and any other laws relevant to target customers,
> and attach the Standard Contractual Clauses where needed.

This Addendum forms part of the agreement between **Divine Group Holdings LLC d/b/a RAMVORA**
("**Processor**") and the customer ("**Controller**") for the RAMVORA service (the "**Agreement**").

## 1. Roles and scope

1.1 For personal data contained in documents the Controller submits ("**Customer Personal Data**"),
the Controller is the controller and RAMVORA is the processor (or "service provider").

1.2 **Subject matter:** extracting structured data from invoices and related business documents.

**Duration:** the term of the Agreement.

**Nature:** automated processing in memory; results returned to the Controller.

**Data subjects:** individuals named on invoices (for example supplier or buyer contacts) and the
Controller's users.

**Data types:** names, business contact details, addresses and tax identifiers as printed on
documents; account identifiers. No special-category data is intended.

## 2. Processor obligations
RAMVORA will:


(a) process Customer Personal Data only on documented instructions (the Agreement and use of the
  API are the instructions), unless required by law, in which case it will inform the Controller
  where permitted;

(b) ensure personnel with access are bound by confidentiality;

(c) implement the security measures in Annex 2;

(d) not sell Customer Personal Data or use it to train machine-learning models;

(e) assist the Controller, taking into account the nature of processing, with data-subject
  requests, security, breach notification and impact assessments;

(f) notify the Controller **without undue delay, and within [48/72] hours**, after becoming aware
  of a personal data breach affecting Customer Personal Data;

(g) at the end of the Agreement, delete Customer Personal Data. Uploaded documents are never
  stored, and account records are deleted on account deletion; backup copies expire as described
  in Annex 2;

(h) make available information needed to demonstrate compliance and allow reasonable audits
  [ONCE PER YEAR, ON 30 DAYS' NOTICE, AT CONTROLLER'S COST; OR VIA A SECURITY QUESTIONNAIRE].

## 3. Sub-processors

3.1 The Controller authorises the sub-processors in Annex 1.

3.2 RAMVORA will give **[30] days'** notice of new sub-processors by email or by updating the
published list, and the Controller may object on reasonable data-protection grounds. If the
objection cannot be resolved, the Controller may terminate the affected service.

3.3 RAMVORA imposes data-protection obligations on each sub-processor that are no less protective
than this Addendum and remains responsible for their performance.

## 4. International transfers
Where Customer Personal Data is transferred outside the EEA/UK to a country without an adequacy
decision, the parties agree to the applicable **Standard Contractual Clauses** (Module 2/3) and UK
Addendum, incorporated by reference. [COUNSEL TO COMPLETE.]

## 5. Liability
Liability under this Addendum is subject to the limitations in the Agreement, [EXCEPT AS COUNSEL
ADVISES].

---

## Annex 1: Sub-processors

| Sub-processor | Purpose | Location |
|---|---|---|
| Render Services, Inc. | Hosting and database storage | USA (Oregon) |
| Stripe, Inc. | Payments and subscriptions (billing data only) | USA / global |
| Resend | Transactional email (account emails only) | USA |
| Cloudflare, Inc. | DNS, email forwarding, encrypted backup storage (R2) | USA / global |
| *Anthropic PBC (optional, currently disabled)* | *AI extraction engine; only after notice and consent* | *USA* |

## Annex 2: Technical and organisational measures

- **In transit:** TLS for all traffic; HTTPS enforced (HSTS).
- **Documents:** processed in memory, not written to storage. Logs exclude document contents and secrets.
- **Credentials:** API keys stored only as hashes; short-lived encrypted copies for delivery and
  recovery (recovery codes expire after 10 minutes).
- **Backups:** encrypted before upload with a dedicated key. Server copies kept 7 daily, 4 weekly,
  12 monthly; off-site copies (Cloudflare R2, private bucket, bucket-scoped credentials) deleted
  after 400 days. Restore tested on 2026-11-26.
- **Access control:** admin functions need a secret of 32+ characters and a named actor, with
  lockout after failures, rate limits and an append-only audit log. Infrastructure accounts are
  limited to authorised personnel.
- **Abuse protection:** per-key and per-address rate limits; monthly usage caps.
- **Testing:** automated test suite and dependency vulnerability scanning on every change.
