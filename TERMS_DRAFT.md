# RAMVORA Terms of Service: DRAFT FOR LEGAL REVIEW

> **Draft v2 (2026-11-26). Not legal advice. Not approved for publication.**
> Prepared from the deployed product's actual behaviour so a qualified lawyer can review it.
> Bracketed items `[LIKE THIS]` are decisions or placeholders for the owner or counsel.
> Notes marked **Reviewer note** explain why a clause is written the way it is; delete them before publishing.

**Effective date:** [DATE]

**Provider:** Divine Group Holdings LLC, a Wyoming limited liability company, doing business as RAMVORA
(trade name subject to registration) ("**RAMVORA**", "**we**", "**us**").

**Contact:** support@ramvora.io · Billing: billing@ramvora.io · Privacy: privacy@ramvora.io
**Notices:** [REGISTERED AGENT / NOTICE ADDRESS, WYOMING]

By creating an account, purchasing a plan, or using an API key, you ("**Customer**", "**you**")
agree to these Terms. If you accept on behalf of an organisation, you confirm you are authorised to
bind it. **The Service is for businesses and professionals only, not for personal, family or
household use.**

> **Reviewer note:** B2B-only is intended to keep consumer-protection regimes out of scope. Confirm this
> is effective in the target markets (US, EU/UK, Latin America, Caribbean) and whether checkout should
> ask the customer to confirm business use.

## 1. The Service

1.1 RAMVORA provides an application programming interface (API) and dashboard that extract
structured data from invoices and related business documents (text, PDF and image files). This
includes, depending on the endpoint:


(a) header fields such as supplier name, invoice number, invoice date, currency, subtotal, tax,
  discount, shipping and total; and

(b) **beta** commercial-invoice extraction, including seller, buyer, trade terms (Incoterms) and
  line items.

1.2 **Beta features** are provided for evaluation, may change or be withdrawn, and are excluded from
any service commitments.

1.3 **What RAMVORA does not do.** RAMVORA does not:

- classify goods or determine tariff (HS) codes;
- calculate duties, taxes or fees;
- determine origin or customs value;
- prepare, sign or file customs or tax declarations; or
- provide accounting, tax, customs or legal advice.

Where an invoice prints an HS code, RAMVORA may copy it exactly as printed and labels it as such.

## 2. Human review is required

2.1 Extraction is automated and **can be incomplete or wrong**, especially for scanned or
low-quality documents. Every result is marked as requiring review. **You must check every result
against the original document** before relying on it for payment, accounting, tax, customs,
regulatory or other decisions.

2.2 RAMVORA does not promise any accuracy rate. Any accuracy figures we publish describe test
conditions only.

## 3. Accounts and API keys

3.1 API keys are credentials. Keep them secret. You are responsible for all activity under your
keys until you report a compromise to support@ramvora.io. You can rotate or revoke keys through the
API.

3.2 We store only a cryptographic hash of each key. We cannot show you a lost key, but you can
recover access through the email-based recovery process.

3.3 We may suspend or revoke keys to protect the Service, other customers or third parties, to
comply with law, or as described in sections 5 and 6.

## 4. Plans, usage and billing

4.1 **Plans.** Current plans, prices and monthly page allowances are shown at checkout. At the
date of this draft they are:

- Starter: US$19 per month for 1,000 pages;
- Professional: US$49 per month for 5,000 pages;
- Business: US$149 per month for 20,000 pages.

4.2 **Usage unit.** Usage is counted in **pages**:

- each PDF page counts as one page;
- an image or pasted text counts as one page;
- uploads that are rejected (for example unsupported, empty or invalid files) are not counted.

Allowances reset each [CALENDAR MONTH (UTC) / BILLING PERIOD]. Unused pages do not roll over.
Requests above the allowance are refused until the next reset or an upgrade; there are no automatic
overage charges.

> **Reviewer note:** the code currently resets usage by **UTC calendar month**. Confirm wording matches.

4.3 **Payment.** Payments are processed by Stripe. By subscribing, you authorise recurring monthly
charges to your payment method until you cancel. Prices exclude taxes; [TAX COLLECTION POSITION TO
BE CONFIRMED].

4.4 **Failed payments.** If a renewal payment fails, access continues for a grace period of
[72 hours] while payment is retried, and is then paused until payment succeeds.

4.5 **Cancellation.** You can cancel through the Stripe customer portal. Access continues until
the end of the paid period unless stated otherwise at cancellation. Fees already paid are
non-refundable except as required by law or stated in section 5.

## 5. Refunds and payment disputes

5.1 If a payment is **refunded** or **disputed** (chargeback), access for the related account is
**paused pending manual review**. This includes a refund or dispute that is recorded before the
account's API key is created.

5.2 We restore access after review where appropriate. A dispute decided in our favour does not
automatically restore access; it is reviewed first.

5.3 Refund requests: billing@ramvora.io. [REFUND POLICY: e.g. "no refunds for partial months" or
"refund within 7 days of first purchase"; OWNER TO DECIDE.]

## 6. Acceptable use

You must follow the RAMVORA Acceptable Use Policy (incorporated by reference). In short, do not:

- upload documents you are not authorised to process;
- use the Service unlawfully or to infringe others' rights;
- attempt to access other customers' data or bypass security, rate limits or usage limits;
- overload, disrupt, scrape or reverse-engineer the Service; or
- resell the Service without written permission.

We may throttle, suspend or terminate access for violations.

## 7. Customer data

7.1 **Ownership.** You keep all rights in the documents you submit and the data extracted from
them ("**Customer Data**").

7.2 **Processing.** We process Customer Data only to provide, secure and support the Service and
as described in the Privacy Policy and, where it applies, the Data Processing Addendum ("DPA").
Uploaded files are processed in memory and are **not stored** by the API after the request
completes.

7.3 **No training on your data.** We do not use Customer Data to train machine-learning models,
and we do not sell it.

7.4 **Optional AI processing.** If RAMVORA enables an AI extraction engine for your account, we will
tell you in advance, name the provider in the sub-processor list, and obtain any consent required.
At the date of this draft, this engine is **disabled**.

7.5 **Your responsibilities.** You confirm you have the rights and any notices or consents needed
to submit Customer Data, including any personal data it contains.

## 8. Availability, support and changes

8.1 The Service is offered on an early-access basis. We aim for reliable operation, but we do not
guarantee uninterrupted availability or response times unless agreed in writing.

8.2 We may change or discontinue features. We will give reasonable notice of material changes that
reduce paid functionality, and you may cancel if you disagree.

8.3 Support: support@ramvora.io, [BUSINESS HOURS / RESPONSE TARGET].

## 9. Confidentiality and security

Each party will protect the other's non-public information with reasonable care and use it only to
perform these Terms. We maintain the security measures described in the Privacy Policy and DPA,
including encryption in transit, hashed API keys, encrypted backups, access controls and audit
logging.

## 10. Warranties and disclaimers

To the maximum extent permitted by law, the Service is provided "**as is**" and "**as available**".
We disclaim implied warranties of merchantability, fitness for a particular purpose, accuracy and
non-infringement. [COUNSEL TO CONFIRM ENFORCEABILITY BY JURISDICTION.]

## 11. Limitation of liability

11.1 Neither party is liable for indirect, incidental, special, consequential or punitive damages,
or for lost profits, revenue or data, to the extent permitted by law.

11.2 Each party's total liability under these Terms is limited to the **fees paid by Customer in
the [12] months** before the event giving rise to the claim. [COUNSEL TO CONFIRM CAP AND CARVE-OUTS,
e.g. for breach of confidentiality, data-protection obligations, or Customer's payment obligations.]

11.3 Without limiting section 2, RAMVORA is not liable for decisions made using extracted data that
was not reviewed against the original document.

## 12. Indemnity

Customer will defend and indemnify RAMVORA against third-party claims arising from Customer Data
that Customer had no right to submit, or from Customer's breach of section 6.
[COUNSEL: consider a mutual IP indemnity from RAMVORA.]

## 13. Term, suspension and termination

13.1 These Terms apply while you have an account or use the Service.

13.2 You may stop using the Service and delete your account at any time through the API's
account-deletion function, which cancels linked subscriptions and deletes your application
records (see the Privacy Policy for backup and billing-record retention).

13.3 We may suspend or terminate for material breach, non-payment, or legal or security reasons.
Where practical, we will give notice and an opportunity to cure.

## 14. Governing law and disputes

These Terms are governed by the laws of the **State of Wyoming, USA**, excluding conflict-of-law
rules. [COUNSEL TO CHOOSE: courts of Wyoming, OR binding arbitration (e.g. AAA/ICC) with a seat of
[CITY], plus a small-claims carve-out.] Mandatory local law protections are not affected.

## 15. General

- Entire agreement (with the Privacy Policy, AUP, DPA where applicable, and any order form).
- Neither party may assign without consent, except to a successor of its business.
- We may update these Terms by posting a new version with a new effective date and, for material
  changes, notifying you by email at least [30] days in advance.
- If a provision is unenforceable, the rest remains in effect.
- No waiver unless in writing.
- Notices to RAMVORA: support@ramvora.io and the notice address above.
