# RAMVORA — Stripe Sandbox test plan

Status: **CI verified; Stripe end-to-end tests not yet executable**. A read-only inspection of the connected Divine Group Holdings LLC Stripe test-mode account found three active products and monthly prices. No credentials were read, no Stripe objects were changed, and no payment or subscription was created.

## Safe environment

Use a dedicated Stripe **Sandbox** for this integration if available. The connected Divine Group Holdings LLC account currently exposes test mode; the read-only inventory below is from test mode, not Live mode. Keep test and production credentials separate.

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

1. The connected test-mode account already has the three active RAMVORA products and monthly prices listed below. Do not create duplicates.
2. Confirm the owner approves the proposed $19/$49/$149 monthly prices and the included page allowances before using Checkout. These are test-mode prices only; do not create or activate Live prices.
3. Correct the product descriptions in Stripe Dashboard from “requests per month” to “pages per month” before customer-facing checkout; the API meters pages, so “requests” is inaccurate. This plan records the mismatch but does not change Stripe objects.
4. Configure the test-mode webhook destination to the staging API's `/v1/billing/webhook`. No test-mode webhook endpoint currently exists. Subscribe only to events handled by the application:
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded` (confirm handler behavior before relying on delayed payment methods)
   - `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`
   - `invoice.paid`, `invoice.payment_failed`
   - `charge.refunded`
   - `charge.dispute.created`, `charge.dispute.updated`, `charge.dispute.closed`
5. Store the test-mode signing secret in `STRIPE_WEBHOOK_SECRET`. Verify a harmless test webhook reaches the endpoint and is signature-checked.
6. Verify email delivery to a controlled test mailbox before using Checkout. Confirm the message contains the API key only in the intended email and that application logs do not contain it.
7. Confirm the staging service and database are disposable and isolated. Do not deploy or provision paid infrastructure without separate approval.

## Read-only test-mode inventory (2026-11-24)

| Plan | Product ID | Price ID | Test price |
|---|---|---|---:|
| Starter | `prod_VgXCrxASbcQvOr` | `price_1UfA89KqMzLsvG4ZAFDh3MJU` | $19/month |
| Professional | `prod_VgXClEK0tjdJTA` | `price_1UfA8MKqMzLsvG4Zhn16WocE` | $49/month |
| Business | `prod_VgXC8DdMmVCO5j` | `price_1UfA8OKqMzLsvG4ZAM90zuJE` | $149/month |

All three are active monthly USD recurring prices in test mode. No webhook endpoints were found. Existing Stripe product descriptions say “requests per month”; the API's metering unit is pages, so those descriptions must be corrected before customer-facing checkout.

**Update (2026-11-25):** the owner renamed the test-mode products to RAMVORA Starter, RAMVORA Professional and RAMVORA Business, and applied the page-based descriptions from `STRIPE_PLAN_DESCRIPTIONS.md`. Product IDs, price IDs and prices are unchanged. Live mode is untouched.

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
| 21 | Refund or dispute, then a renewal `invoice.paid` / `customer.subscription.updated` while the subscription is still active | Key stays suspended with its refund/dispute status; only manual review restores access |

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

- No separate Stripe Sandbox was confirmed; only the connected account's test mode was inspected.
- No test-mode webhook endpoint exists. No staging API URL, webhook signing secret, test-mode secret key, Resend credentials, verified sender, or isolated staging database has been configured in this workspace.
- The billing module now creates a scoped `StripeClient` per operation and uses the `client.v1` service namespace; webhook signature construction is performed through that client. Automated tests use a test-only adapter and do not contact Stripe.
- The Checkout handler currently uses synchronous Checkout Session creation. Confirm webhook fulfillment for asynchronous payment success and test only payment methods whose lifecycle the handler explicitly supports.
- Tax is intentionally not enabled. Before collecting from US or other jurisdictions, determine registration/collection obligations and complete Stripe Tax setup; enabling automatic tax without active registrations does not by itself make tax collection compliant.
- The test suite's mocked Stripe tests are not a substitute for this live-to-sandbox integration test.

## Evidence log template

For each test, record: date/time, scenario number, sandbox name, test customer email, Stripe object/event IDs, HTTP status, API key state (never the key itself), page allowance, email received, pass/fail, issue link, and reviewer. Redact personal and payment details before sharing evidence.
