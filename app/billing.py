from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
import secrets
from typing import Any

import stripe
from cryptography.fernet import Fernet
from app.security import (
    apply_stripe_subscription_event, checkout_key_delivery, mark_checkout_email_sent,
    provision_checkout_key, record_stripe_event, get_key_record_by_customer_id,
    create_recovery_code, prepare_recovery_key, mark_recovery_email_sent,
    suspend_customer_access, claim_checkout_email_delivery, release_checkout_email_delivery,
)
from app.email_delivery import send_api_key_email, send_recovery_code_email

PLAN_PRICE_ENV = {
    "starter": "STRIPE_PRICE_STARTER",
    "professional": "STRIPE_PRICE_PROFESSIONAL",
    "business": "STRIPE_PRICE_BUSINESS",
}
PLAN_LIMIT_ENV = {
    "starter": "PLAN_STARTER_MONTHLY_LIMIT",
    "professional": "PLAN_PROFESSIONAL_MONTHLY_LIMIT",
    "business": "PLAN_BUSINESS_MONTHLY_LIMIT",
}
DEFAULT_LIMITS = {"starter": 1000, "professional": 5000, "business": 20000}
logger = logging.getLogger(__name__)


def _configure() -> None:
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("Stripe billing is not configured.")
    stripe.api_key = secret


def _monthly_limit(plan: str) -> int:
    return int(os.getenv(PLAN_LIMIT_ENV[plan], str(DEFAULT_LIMITS[plan])))


def _within_payment_grace(record: dict[str, Any]) -> bool:
    started = record.get("past_due_since")
    if not started:
        return False
    try:
        past_due_at = datetime.fromisoformat(started)
    except (TypeError, ValueError):
        return False
    if past_due_at.tzinfo is None:
        past_due_at = past_due_at.replace(tzinfo=timezone.utc)
    grace_hours = int(os.getenv("PAYMENT_GRACE_HOURS", "72"))
    return datetime.now(timezone.utc) - past_due_at <= timedelta(hours=grace_hours)


def _stripe_period_value(subscription: Any, field: str) -> str | None:
    value = subscription.get(field)
    if value is None:
        # Newer Stripe API versions may expose billing periods on subscription items.
        items = (subscription.get("items") or {}).get("data") or []
        value = next((item.get(field) for item in items if item.get(field) is not None), None)
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        logger.warning("Stripe subscription returned an invalid %s timestamp.", field)
        return None


def create_checkout_session(plan: str, email: str) -> str:
    _configure()
    if not all(os.getenv(name) for name in ("API_KEY_ENCRYPTION_KEY", "RESEND_API_KEY", "FROM_EMAIL")):
        raise RuntimeError("Secure API-key encryption and email delivery must be configured before accepting paid signups.")
    try:
        Fernet(os.environ["API_KEY_ENCRYPTION_KEY"].encode("ascii"))
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must be a valid Fernet key before accepting paid signups.") from exc
    price_id = os.getenv(PLAN_PRICE_ENV[plan])
    if not price_id:
        raise RuntimeError(f"The Stripe price for {plan} is not configured.")
    success_url = os.getenv("CHECKOUT_SUCCESS_URL")
    cancel_url = os.getenv("CHECKOUT_CANCEL_URL")
    if not success_url or not cancel_url:
        raise RuntimeError("Checkout success and cancel URLs are not configured.")
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"plan": plan, "signup_email": email},
        subscription_data={"metadata": {"plan": plan, "signup_email": email}},
    )
    return str(session.url)


def claim_checkout_key(session_id: str) -> str:
    """Legacy browser claim. Kept temporarily for existing checkout sessions."""
    _configure()
    session = stripe.checkout.Session.retrieve(session_id)
    if session.get("status") != "complete" or session.get("mode") != "subscription":
        raise ValueError("Checkout has not been completed.")
    if session.get("payment_status") not in {"paid", "no_payment_required"}:
        raise ValueError("Payment has not been confirmed yet.")
    metadata = session.get("metadata") or {}
    plan = metadata.get("plan")
    email = (
        (session.get("customer_details") or {}).get("email")
        or session.get("customer_email")
        or metadata.get("signup_email")
    )
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    if plan not in PLAN_PRICE_ENV or not email or not customer_id or not subscription_id:
        raise ValueError("The completed checkout is missing required subscription details.")
    subscription = stripe.Subscription.retrieve(subscription_id)
    status = str(subscription.get("status", "incomplete"))
    if status not in {"active", "trialing"}:
        raise ValueError("The subscription is not active. Please contact support.")
    return provision_checkout_key(
        session_id, email, plan, str(customer_id), str(subscription_id),
        _monthly_limit(plan), claim=True,
        current_period_start=_stripe_period_value(subscription, "current_period_start"),
        current_period_end=_stripe_period_value(subscription, "current_period_end"),
    )


def cancel_customer_subscriptions(customer_id: str) -> None:
    """Cancel all non-terminal subscriptions before local customer data is erased."""
    _configure()
    subscriptions = stripe.Subscription.list(customer=customer_id, status="all", limit=100)
    for subscription in subscriptions.get("data", []):
        status = str(subscription.get("status", ""))
        subscription_id = str(subscription.get("id") or "")
        if subscription_id and status not in {"canceled", "incomplete_expired"}:
            stripe.Subscription.cancel(subscription_id)


def create_portal_session(key_record: dict[str, Any]) -> str:
    _configure()
    customer_id = key_record.get("stripe_customer_id")
    if not customer_id:
        raise ValueError("No Stripe customer is associated with this API key.")
    return_url = os.getenv("CUSTOMER_PORTAL_RETURN_URL")
    if not return_url:
        raise RuntimeError("Customer portal return URL is not configured.")
    return str(
        stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url).url
    )


def request_api_key_recovery(email: str) -> None:
    _configure()
    if not all(os.getenv(name) for name in ("API_KEY_ENCRYPTION_KEY", "RESEND_API_KEY", "FROM_EMAIL")):
        raise RuntimeError("Secure key encryption and email delivery are not configured.")
    try:
        Fernet(os.environ["API_KEY_ENCRYPTION_KEY"].encode("ascii"))
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY is invalid.") from exc
    try:
        customers = stripe.Customer.list(email=email, limit=10)
    except Exception:
        logger.warning("Stripe customer lookup failed during account recovery.")
        return
    for customer in customers.get("data", []):
        customer_id = str(customer.get("id") or "")
        record = get_key_record_by_customer_id(customer_id)
        if not record or not record["active"] or not record.get("subscription_id"):
            continue
        subscription = stripe.Subscription.retrieve(record["subscription_id"])
        status = str(subscription.get("status", "canceled"))
        if status not in {"active", "trialing", "past_due"}:
            continue
        if status == "past_due" and not _within_payment_grace(record):
            continue
        code = f"{secrets.randbelow(1_000_000):06d}"
        create_recovery_code(email, customer_id, code)
        try:
            send_recovery_code_email(email, code)
        except Exception:
            logger.warning("Recovery email delivery failed.")
        return
    # Do not disclose whether an email has an account or active subscription.


def confirm_api_key_recovery(email: str, code: str) -> None:
    _configure()
    # Validate billing eligibility before consuming the one-time code or rotating credentials.
    # Rotation and encrypted pending delivery are committed atomically; retries reuse that key.
    try:
        customers = stripe.Customer.list(email=email, limit=10)
    except Exception as exc:
        raise RuntimeError("Unable to verify the billing account for recovery.") from exc
    for customer in customers.get("data", []):
        customer_id = str(customer.get("id") or "")
        record = get_key_record_by_customer_id(customer_id)
        if not record or not record["active"] or not record.get("subscription_id"):
            continue
        subscription = stripe.Subscription.retrieve(record["subscription_id"])
        status = str(subscription.get("status", "canceled"))
        if status not in {"active", "trialing", "past_due"}:
            continue
        if status == "past_due" and not _within_payment_grace(record):
            continue
        new_key = prepare_recovery_key(email, code, customer_id, record["id"])
        if not new_key:
            continue
        send_api_key_email(email, new_key)
        mark_recovery_email_sent(email, code)
        return
    raise ValueError("The recovery code is invalid, expired, or already used, or the account is not eligible.")

def _subscription_plan(subscription: Any) -> str | None:
    """Resolve one unambiguous plan from all configured subscription item prices."""
    items = subscription.get("items") or {}
    data = items.get("data") or []
    configured_prices = {
        os.getenv(env_name): plan
        for plan, env_name in PLAN_PRICE_ENV.items()
        if os.getenv(env_name)
    }
    matched = {
        configured_prices.get(str((item.get("price") or {}).get("id")))
        for item in data
        if str((item.get("price") or {}).get("id")) in configured_prices
    }
    matched.discard(None)
    if len(matched) > 1:
        logger.error("Stripe subscription has multiple configured plan prices; retaining the existing entitlement.")
        return None
    if len(matched) == 1:
        return next(iter(matched))
    metadata = subscription.get("metadata") or {}
    plan = metadata.get("plan")
    return plan if plan in PLAN_PRICE_ENV else None


def _invoice_subscription_id(invoice: Any) -> str | None:
    subscription_id = invoice.get("subscription")
    if subscription_id:
        return str(subscription_id)
    parent = invoice.get("parent") or {}
    details = parent.get("subscription_details") or {}
    subscription_id = details.get("subscription")
    return str(subscription_id) if subscription_id else None


def _apply_subscription_event(event: Any, event_type: str, subscription_id: str) -> str:
    event_obj = event["data"]["object"]
    try:
        # Always reconcile against Stripe's current object. A delayed webhook
        # must not overwrite a newer subscription state with an old snapshot.
        current = stripe.Subscription.retrieve(subscription_id)
    except Exception:
        if event_type == "customer.subscription.deleted":
            current = event_obj
        else:
            raise
    status = str(current.get("status", event_obj.get("status", "canceled")))
    if current.get("pause_collection"):
        status = "paused"
    plan = _subscription_plan(current) or _subscription_plan(event_obj)
    customer_id = current.get("customer") or event_obj.get("customer")
    event_id = event.get("id")
    if not event_id:
        raise ValueError("Stripe webhook event is missing its event ID.")
    return apply_stripe_subscription_event(
        str(event_id),
        int(event.get("created") or 0),
        event_type,
        subscription_id,
        status,
        plan,
        str(customer_id) if customer_id else None,
        _monthly_limit(plan) if plan else None,
        _stripe_period_value(current, "current_period_start"),
        _stripe_period_value(current, "current_period_end"),
    )


def _deliver_checkout_key(session: Any) -> str:
    if session.get("status") != "complete" or session.get("mode") != "subscription":
        return "not_complete"
    if session.get("payment_status") not in {"paid", "no_payment_required"}:
        return "payment_pending"
    metadata = session.get("metadata") or {}
    session_id = str(session.get("id") or "")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")
    email = (
        (session.get("customer_details") or {}).get("email")
        or session.get("customer_email")
        or metadata.get("signup_email")
    )
    if not session_id or not subscription_id or not customer_id or not email:
        raise ValueError("Completed Checkout session is missing customer or subscription details.")
    current = stripe.Subscription.retrieve(str(subscription_id))
    status = str(current.get("status", "incomplete"))
    if status not in {"active", "trialing"}:
        raise RuntimeError("The Stripe subscription is not active yet; key delivery will retry.")
    plan = _subscription_plan(current) or metadata.get("plan")
    if plan not in PLAN_PRICE_ENV:
        raise ValueError("Unable to map the completed Checkout subscription to a configured plan.")
    provision_checkout_key(
        session_id, str(email), plan, str(customer_id), str(subscription_id),
        _monthly_limit(plan), claim=False,
        current_period_start=_stripe_period_value(current, "current_period_start"),
        current_period_end=_stripe_period_value(current, "current_period_end"),
    )
    delivery = checkout_key_delivery(session_id)
    if not delivery:
        raise RuntimeError("The provisioned API key could not be loaded for email delivery.")
    if not delivery["email_sent_at"]:
        if not claim_checkout_email_delivery(session_id):
            return "delivery_in_progress"
        try:
            send_api_key_email(str(delivery["email"]), str(delivery["api_key"]))
            mark_checkout_email_sent(session_id)
        except Exception:
            release_checkout_email_delivery(session_id)
            raise
    return "email_delivered"


def _suspend_charge_customer(charge_or_dispute: Any, reason: str) -> int:
    customer_id = charge_or_dispute.get("customer")
    if not customer_id:
        charge_id = charge_or_dispute.get("charge")
        if isinstance(charge_id, dict):
            customer_id = charge_id.get("customer")
        elif charge_id:
            charge = stripe.Charge.retrieve(str(charge_id))
            customer_id = charge.get("customer")
    if not customer_id:
        logger.error("Cannot suspend access for %s event: Stripe customer ID is missing.", reason)
        raise ValueError("Stripe billing event is missing the customer reference.")
    return suspend_customer_access(str(customer_id), reason)


def handle_webhook(payload: bytes, signature: str | None) -> dict[str, str]:
    _configure()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise RuntimeError("Stripe webhook signing secret is not configured.")
    if not signature:
        raise ValueError("Missing Stripe-Signature header.")
    try:
        event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
    except Exception as exc:
        if exc.__class__.__name__ == "SignatureVerificationError":
            raise ValueError("Invalid Stripe webhook signature.") from exc
        raise

    event_type = event["type"]
    obj = event["data"]["object"]
    event_id = event.get("id")
    if not event_id:
        raise ValueError("Stripe webhook event is missing its event ID.")
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        outcome = _deliver_checkout_key(obj)
        # Record only after delivery succeeds. If email delivery fails, Stripe
        # retries and the encrypted key is reused rather than regenerated.
        if outcome == "email_delivered":
            record_stripe_event(str(event_id), int(event.get("created") or 0), event_type)
    elif event_type in {
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }:
        subscription_id = str(obj.get("id") or "")
        if not subscription_id:
            raise ValueError("Stripe subscription event is missing its subscription ID.")
        outcome = _apply_subscription_event(event, event_type, subscription_id)
    elif event_type == "charge.refunded":
        amount = int(obj.get("amount") or 0)
        refunded = int(obj.get("amount_refunded") or 0)
        reason = "refunded" if amount > 0 and refunded >= amount else "refund_review"
        changed = _suspend_charge_customer(obj, reason)
        outcome = record_stripe_event(str(event_id), int(event.get("created") or 0), event_type)
        logger.warning("Suspended %s API key(s) for Stripe refund event (%s).", changed, reason)
    elif event_type in {"charge.dispute.created", "charge.dispute.updated", "charge.dispute.closed"}:
        changed = _suspend_charge_customer(obj, "disputed")
        outcome = record_stripe_event(str(event_id), int(event.get("created") or 0), event_type)
        logger.warning("Suspended %s API key(s) pending manual review of Stripe dispute.", changed)
    elif event_type in {"invoice.payment_failed", "invoice.paid"}:
        subscription_id = _invoice_subscription_id(obj)
        if subscription_id:
            outcome = _apply_subscription_event(event, event_type, subscription_id)
        else:
            outcome = record_stripe_event(
                str(event.get("id") or ""), int(event.get("created") or 0), event_type
            )
    else:
        outcome = record_stripe_event(
            str(event.get("id") or ""), int(event.get("created") or 0), event_type
        )
    return {"received": "true", "event_type": event_type, "outcome": outcome}
