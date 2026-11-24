from __future__ import annotations

import os
from typing import Any

import stripe
from app.security import (
    apply_stripe_subscription_event, provision_checkout_key, record_stripe_event,
)

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


def _configure() -> None:
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("Stripe billing is not configured.")
    stripe.api_key = secret


def _monthly_limit(plan: str) -> int:
    return int(os.getenv(PLAN_LIMIT_ENV[plan], str(DEFAULT_LIMITS[plan])))


def create_checkout_session(plan: str, email: str) -> str:
    _configure()
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
        success_url=success_url + ("&" if "?" in success_url else "?") + "session_id={CHECKOUT_SESSION_ID}",
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
    raw_key = provision_checkout_key(
        session_id, email, plan, str(customer_id), str(subscription_id), _monthly_limit(plan)
    )
    if not raw_key:
        raise ValueError("This checkout session's API key has already been claimed. Contact support for recovery.")
    return raw_key


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


def _subscription_plan(subscription: Any) -> str | None:
    """Resolve the current plan from its active Stripe price, not stale metadata."""
    items = subscription.get("items") or {}
    data = items.get("data") or []
    price_id = None
    if data:
        price = data[0].get("price") or {}
        price_id = price.get("id")
    if price_id:
        for plan, env_name in PLAN_PRICE_ENV.items():
            configured = os.getenv(env_name)
            if configured and configured == price_id:
                return plan
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
    )


def handle_webhook(payload: bytes, signature: str | None) -> dict[str, str]:
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
    if event_type in {
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }:
        subscription_id = str(obj.get("id") or "")
        if not subscription_id:
            raise ValueError("Stripe subscription event is missing its subscription ID.")
        outcome = _apply_subscription_event(event, event_type, subscription_id)
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
