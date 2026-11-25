# Administrator guide

The admin API lets an operator review customers, suspend or restore access, read
Stripe billing events, find stuck key emails and read the audit trail. It is
**not** listed in the public `/docs` page.

## Security settings

| Variable | Purpose |
| --- | --- |
| `API_ADMIN_KEY` | Required. At least 32 characters (Render generates one). Sent as `X-Admin-Key`. Never share it or put it in a browser. |
| `ADMIN_ALLOWED_IPS` | Strongly recommended. Comma-separated IPs/CIDRs allowed to reach admin routes (e.g. your office or VPN). Everyone else gets 404. |
| `ADMIN_AUTH_FAILURE_LIMIT` | Failed key attempts per client per hour before a 1-hour lockout (default 10). |
| `ADMIN_RATE_LIMIT` | Admin requests per client per hour (default 300). |
| `ADMIN_CREATE_KEY_RATE_LIMIT` | Manual key creations per client per hour (default 10). |
| `TRUSTED_PROXY_HOPS` | Proxies in front of the app (Render: `1`). Used to find the real client IP for allowlists, rate limits and audit. |

Every admin request, including failed logins, is written to `admin_audit_log`
with the actor name, action, target, a hashed client identifier and the result.
Keys are never logged. Changes (`hold`, `clear-hold`, creating keys) require an
`X-Admin-Actor` header with your name.

## Examples

```bash
export QV=https://<your-service>.onrender.com
export AK='<API_ADMIN_KEY from Render — never commit it>'
H=(-H "X-Admin-Key: $AK" -H "X-Admin-Actor: Your Name")

# Customers under a billing hold
curl "${H[@]}" "$QV/v1/admin/customers?hold_only=true"

# Search by email or Stripe customer ID
curl "${H[@]}" "$QV/v1/admin/customers?search=buyer@example.com"

# One customer: status, hold, usage, Stripe events, email delivery, admin history
curl "${H[@]}" "$QV/v1/admin/customers/42"

# Suspend access (applies to every key of that Stripe customer)
curl "${H[@]}" -H 'content-type: application/json' \
  -d '{"note":"abuse report #123"}' "$QV/v1/admin/customers/42/hold"

# Restore access after review
curl "${H[@]}" -H 'content-type: application/json' \
  -d '{"note":"dispute withdrawn, confirmed in Stripe"}' "$QV/v1/admin/customers/42/clear-hold"

# Stripe billing events (optionally ?customer_id=cus_... or ?event_type=charge.refunded)
curl "${H[@]}" "$QV/v1/admin/billing-events"

# API-key emails that have not been delivered
curl "${H[@]}" "$QV/v1/admin/email-deliveries/pending"

# Audit trail (add ?failures_only=true to see rejected attempts)
curl "${H[@]}" "$QV/v1/admin/audit-log"
```

## How holds work

- A refund or dispute webhook places an **access hold** (`refunded`,
  `refund_review`, `disputed`, `dispute_lost`). An admin hold is `manual_review`.
- `subscription_status` always shows Stripe's real status. A hold is separate
  and **no Stripe event removes it**, including renewals, a dispute won, or
  cancellation.
- `clear-hold` lifts the hold. Access comes back only if Stripe's subscription
  still grants it (`active`, `trialing`, or `past_due` within the grace period)
  and the customer has not revoked the key. The response says whether access
  was restored.
- After a hold is cleared, refund or dispute events created *before* that
  moment (delayed or redelivered) cannot re-suspend the customer. A new dispute
  created afterwards will.
- If a held Stripe customer subscribes again, the new key inherits the hold.

Before clearing a hold, check the charge, refund or dispute in the Stripe
Dashboard and record the outcome in the `note`.
