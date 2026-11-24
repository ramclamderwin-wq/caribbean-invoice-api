from __future__ import annotations

import os
from typing import Any

import stripe

from app.security import set_subscription, set_subscription_by_id

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


def _configure() -> None:
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("Stripe billing is not configured.")
    stripe.api_key = secret


def create_checkout_session(key_record: dict[str, Any], plan: str, email: str) -> str:
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
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(key_record["id"]),
        metadata={"api_key_id": str(key_record["id"]), "plan": plan},
        subscription_data={
            "metadata": {"api_key_id": str(key_record["id"]), "plan": plan}
        },
    )
    return str(session.url)


def create_portal_session(key_record: dict[str, Any]) -> str:
    _configure()
    customer_id = key_record.get("stripe_customer_id")
    if not customer_id:
        raise ValueError("No Stripe customer is associated with this API key.")
    return_url = os.getenv("CUSTOMER_PORTAL_RETURN_URL")
    if not return_url:
        raise RuntimeError("Customer portal return URL is not configured.")
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return str(session.url)


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

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        metadata = obj.get("metadata") or {}
        key_id = metadata.get("api_key_id") or obj.get("client_reference_id")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")
        if key_id and subscription_id:
            subscription = stripe.Subscription.retrieve(subscription_id)
            sub_metadata = subscription.get("metadata") or metadata
            plan = sub_metadata.get("plan") or metadata.get("plan") or "starter"
            set_subscription(
                int(key_id),
                plan,
                str(subscription.get("status", "incomplete")),
                str(customer_id) if customer_id else None,
                str(subscription_id),
                _monthly_limit(plan),
            )

    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        metadata = obj.get("metadata") or {}
        key_id = metadata.get("api_key_id")
        plan = metadata.get("plan") or "starter"
        if key_id:
            set_subscription(
                int(key_id),
                plan,
                str(obj.get("status", "canceled")),
                str(obj.get("customer")) if obj.get("customer") else None,
                str(obj.get("id")),
                _monthly_limit(plan),
            )
        elif obj.get("id"):
            set_subscription_by_id(
                str(obj["id"]),
                str(obj.get("status", "canceled")),
            )

    elif event_type == "invoice.payment_failed":
        subscription_id = obj.get("subscription")
        if subscription_id:
            set_subscription_by_id(str(subscription_id), "past_due")

    return {"received": "true", "event_type": event_type}


def _monthly_limit(plan: str) -> int:
    default = {"starter": 1000, "professional": 5000, "business": 20000}
    return int(os.getenv(PLAN_LIMIT_ENV[plan], str(default[plan])))
