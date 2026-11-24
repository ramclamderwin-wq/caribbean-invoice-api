# Quillvora Privacy Notice — DRAFT FOR LEGAL REVIEW

**Not approved for publication.** Complete the placeholders, confirm retention periods and processor contracts, and obtain privacy counsel review before accepting customers.

Controller: Divine Group Holdings LLC, a Wyoming limited liability company, doing business as Quillvora.  
Privacy contact: [PRIVACY EMAIL]  
Postal address: [LEGAL NOTICE ADDRESS]  
Effective date: [DATE]

## 1. Information we process
Depending on how you use Quillvora, we may process:
- Account and billing identifiers, including email address, Stripe customer/subscription identifiers, API-key hashes, plan, and account status.
- API usage events, timestamps, request metadata, security/rate-limit events, and diagnostic logs.
- Invoice text, PDFs, and image files submitted for extraction.

## 2. Invoice content
The API processes invoice uploads in memory for extraction and does not intentionally store the uploaded invoice file or extracted invoice content as a persistent customer document. Operational logs must not include invoice bodies, API keys, or payment details. This description must be re-verified against the deployed service and all error-monitoring configuration.

## 3. Purposes and legal bases
We use account information to provide the service, authenticate requests, meter usage, deliver API keys, administer subscriptions, prevent abuse, provide support, comply with law, and protect the service. For users in jurisdictions requiring a legal-basis disclosure, the final notice must identify the applicable contractual, legitimate-interest, consent, or legal-obligation basis for each purpose.

## 4. Service providers
Expected providers include:
- Render — application hosting and persistent database storage.
- Stripe — checkout, subscription administration, payment processing, and billing records.
- Resend — transactional email delivery, including API-key and recovery-code emails.

Confirm the exact providers, regions, subprocessors, data-processing terms, and international transfer safeguards before publication.

## 5. Retention
The final policy must state and operationally enforce retention periods for account data, usage records, security logs, recovery codes, email delivery records, backups, and billing records. Proposed targets (not yet verified as implemented): recovery codes are short-lived; operational logs are retained for [PERIOD]; usage records for [PERIOD]; account records until account deletion; backups expire after [PERIOD]. Stripe may retain transaction and invoice records as required by law.

## 6. Security
API keys are stored as cryptographic hashes; encrypted temporary copies are used only where necessary for initial key delivery and recovery. Data is transmitted over TLS when the service is correctly deployed behind HTTPS. No security measure is perfect; report suspected compromise to [SECURITY EMAIL].

## 7. Your rights and deletion
Depending on your location, you may have rights to access, correct, delete, restrict, object to, or receive a copy of personal data. The API's account-deletion endpoint cancels associated Stripe subscriptions and removes linked application records. Stripe may retain payment and invoice records for legal, tax, fraud-prevention, and accounting purposes. Contact [PRIVACY EMAIL] for requests that cannot be completed through the API.

## 8. International transfers
The service is operated from infrastructure that may process data in the United States and other locations used by our providers. The final notice must identify relevant transfer mechanisms and safeguards for users in the EEA, UK, and other regulated jurisdictions.

## 9. Children
The service is intended for business users and is not directed to children.

## 10. Updates
We may update this notice as the service changes. The current version and effective date will be published at [PRIVACY NOTICE URL].
