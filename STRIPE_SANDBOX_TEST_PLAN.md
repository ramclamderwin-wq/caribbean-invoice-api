# Quillvora — Stripe Sandbox test plan

Status: **prepared, not executed**. No Stripe account was accessed, no credentials were read, and no payment or subscription was created.

## Safe environment

Use a dedicated Stripe **Sandbox** for this integration (not Live mode and preferably not the account-wide shared test mode). Keep sandbox credentials separate from production credentials.

Required server environment variables for this repository:

- `STRIPE_SECRET_KEY`: sandbox secret key only (`sk_test_...` or sandbox-issued equivalent).
- `STRIPE_WEBHOOK_SECRET`: signing secret from the sandbox webhook endpoint.
- `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PROFESSIONAL`, `STRIPE_PRICE_BUSINESS`: Price IDs created in that same sandbox.
- `API_KEY_ENCRYPTION_KEY`: valid Fernet key generated for the sandbox environment.
- `RESEND_API_KEY` and `FROM_EMAIL`: email delivery credentials and a verified sender. Prefer a controlled test inbox/domain.
- `CHECKOUT_SUCCESS_URL`, `CHECKOUT_CANCEL_URL`, `CUSTOMER_PORTAL_RETURN_URL`: HTTPS URLs for the test/staging app.
- `DATABASE_PATH`: a separate disposable sandbox database, never production data.

Do not paste keys into chat, GitHub, issue comments, screenshots, or source files. Configure them only in a protected local environment or a dedicated staging secret store. Never point a sandbox app at the production database or production email sender.

## Before the first Checkout test

1. In Stripe Dashboard, create a dedicated Sandbox and confirm the dashboard is visibly in that sandbox.
2. Create three separate Products: Quillvora Starter, Quillvora Professional, and Quillvora Business. Create monthly recurring Prices for each. Record the three Price IDs.
3. Confirm prices match the current intended offer in the repository docs: Starter $19/month (1,000 pages), Professional $49/month (5,000 pages), Business $149/month (20,000 pages). Treat these as proposed prices until the owner approves them; don't activate live prices.
4. Configure the sandbox webhook destination to the staging API's `/v1/billing/webhook`. Subscribe only to events handled by the application:
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded` (confirm handler behavior before relying on delayed payment methods)
   - `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`
   - `invoice.paid`, `invoice.payment_failed`
   - `charge.refunded`
   - `charge.dispute.created`, `charge.dispute.updated`, `charge.dispute.closed`
5. Store the sandbox signing secret in `STRIPE_WEBHOOK_SECRET`. Verify a harmless test webhook reaches the endpoint and is signature-checked.
6. Verify email delivery to a controlled test mailbox before using Checkout. Confirm the message contains the API key only in the intended email and that application logs do not contain it.
7. Confirm the staging service and database are disposable and isolated. Do not deploy or provision paid infrastructure without separate approval.

## Execution checklist

Run each scenario with a unique test email/customer and record the Stripe event IDs, expected API result, observed API result, and evidence. Do not mark a test passed without verifying both Stripe state and API access state.

| # | Scenario | Expected result |
|---|---|---|
| 1 | Starter Checkout, successful test payment | Checkout completes; signed webhook provisions exactly one active key; one email delivered |
| 2 | Duplicate delivery of the same checkout webhook | No second key and no duplicate email |
| 3 | Out-of-order subscription events | Older event does not overwrite newer Stripe state |
| 4 | Invalid webhook signature | HTTP 400; no entitlement changes |
| 5 | Professional upgrade | Correct plan and 5,000-page allowance after Stripe subscription update |
| 6 | Starter downgrade | Correct plan and 1,000-page allowance after update |
| 7 | Renewal paid | Access remains active; billing-period page window updates |
| 8 | Renewal payment fails | Access enters configured grace period; no premature suspension |
| 9 | Payment recovers | Access returns to active after authoritative Stripe event |
| 10 | Grace period expires without recovery | API access is suspended |
| 11 | Cancel at period end / cancellation | Access follows actual Stripe subscription status and configured cancellation policy |
| 12 | Pause collection | API access is suspended while paused |
| 13 | Resume collection | Access is restored only after authoritative active subscription state |
| 14 | Full refund | API key is suspended as refunded |
| 15 | Partial refund | API key enters manual-review state |
| 16 | Dispute opened/updated/closed | Access is suspended; closure does not silently auto-reactivate |
| 17 | Customer Portal | Active customer can open portal; revoked/inactive key cannot |
| 18 | Key recovery | Email code verifies; key rotates once; retries do not rotate again |
| 19 | Key rotation and revocation | Old key immediately stops authenticating |
| 20 | Account deletion | Stripe subscriptions are cancelled first; local account data is deleted only after successful cancellation |

## Test payment details

Use Stripe's official test payment methods and test clocks / test event tools where supported. Never use a real card or real bank account. For a failed payment, use Stripe's documented test payment method for the desired failure case; do not guess card numbers from memory. Test dispute and refund events through the sandbox Dashboard or Stripe's documented test mechanisms.

## Pass criteria

- Every scenario above has a dated result and evidence.
- Webhook retries are idempotent; duplicate/out-of-order events do not corrupt entitlements.
- Exactly one API key is provisioned per successful Checkout session.
- API key delivery is reliable and secrets are not exposed in browser URLs or logs.
- Usage quotas and billing periods match the actual subscription and plan.
- Failed payment, refund, dispute, pause, recovery, and deletion behaviors match the policy.
- No sandbox objects or credentials are mixed with Live mode.

## Current blockers / limitations

- The connected Stripe account has not been inspected and no Sandbox credentials are available in this repository context.
- No sandbox Products, Prices, webhook endpoint, verified sender, or staging API have been configured here.
- The billing module now creates a scoped `StripeClient` per operation and uses the `client.v1` service namespace; webhook signature construction is performed through that client. Automated tests use a test-only adapter and do not contact Stripe.
- The Checkout handler currently uses synchronous Checkout Session creation. Confirm webhook fulfillment for asynchronous payment success and test only payment methods whose lifecycle the handler explicitly supports.
- Tax is intentionally not enabled. Before collecting from US or other jurisdictions, determine registration/collection obligations and complete Stripe Tax setup; enabling automatic tax without active registrations does not by itself make tax collection compliant.
- The test suite's mocked Stripe tests are not a substitute for this live-to-sandbox integration test.

## Evidence log template

For each test, record: date/time, scenario number, sandbox name, test customer email, Stripe object/event IDs, HTTP status, API key state (never the key itself), page allowance, email received, pass/fail, issue link, and reviewer. Redact personal and payment details before sharing evidence.
