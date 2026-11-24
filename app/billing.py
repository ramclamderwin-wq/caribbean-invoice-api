from __future__ import annotations
import os
from typing import Any
import stripe
from app.security import create_paid_customer_key, set_subscription, set_subscription_by_id
PLAN_PRICE_ENV={"starter":"STRIPE_PRICE_STARTER","professional":"STRIPE_PRICE_PROFESSIONAL","business":"STRIPE_PRICE_BUSINESS"}
PLAN_LIMIT_ENV={"starter":"PLAN_STARTER_MONTHLY_LIMIT","professional":"PLAN_PROFESSIONAL_MONTHLY_LIMIT","business":"PLAN_BUSINESS_MONTHLY_LIMIT"}
PLAN_DEFAULT_LIMIT={"starter":1000,"professional":5000,"business":20000}
def _configure()->None:
    secret=os.getenv("STRIPE_SECRET_KEY")
    if not secret: raise RuntimeError("Stripe billing is not configured.")
    stripe.api_key=secret
def create_checkout_session(plan:str,email:str)->str:
    _configure()
    if plan not in PLAN_PRICE_ENV: raise ValueError("Unsupported subscription plan.")
    price=os.getenv(PLAN_PRICE_ENV[plan])
    if not price: raise RuntimeError(f"The Stripe price for {plan} is not configured.")
    success,cancel=os.getenv("CHECKOUT_SUCCESS_URL"),os.getenv("CHECKOUT_CANCEL_URL")
    if not success or not cancel: raise RuntimeError("Checkout success and cancel URLs are not configured.")
    s=stripe.checkout.Session.create(mode="subscription",customer_email=email,line_items=[{"price":price,"quantity":1}],
        success_url=success,cancel_url=cancel,metadata={"plan":plan},subscription_data={"metadata":{"plan":plan}})
    return str(s.url)
def claim_checkout_session(session_id:str)->str:
    _configure()
    if not session_id.startswith("cs_"): raise ValueError("Invalid Checkout Session.")
    s=stripe.checkout.Session.retrieve(session_id,expand=["subscription"])
    if s.get("mode")!="subscription" or s.get("payment_status") not in {"paid","no_payment_required"}:
        raise ValueError("Payment is not confirmed yet. Refresh this page in a moment.")
    metadata=s.get("metadata") or {}; plan=metadata.get("plan")
    if plan not in PLAN_PRICE_ENV: raise ValueError("The selected subscription plan could not be verified.")
    sub=s.get("subscription")
    if isinstance(sub,str): sub=stripe.Subscription.retrieve(sub)
    if not sub or sub.get("status") not in {"active","trialing"}: raise ValueError("The subscription is not active yet.")
    email=(s.get("customer_details") or {}).get("email") or s.get("customer_email")
    customer=s.get("customer"); sub_id=sub.get("id")
    if not email or not customer or not sub_id: raise ValueError("Stripe did not return required customer details.")
    limit=int(os.getenv(PLAN_LIMIT_ENV[plan],str(PLAN_DEFAULT_LIMIT[plan])))
    key=create_paid_customer_key(session_id,email,plan,str(customer),str(sub_id),limit)
    if not key: raise ValueError("This Checkout Session was already claimed. The API key is shown only once; contact support if you did not save it.")
    return key
def create_portal_session(key_record:dict[str,Any])->str:
    _configure(); customer=key_record.get("stripe_customer_id")
    if not customer: raise ValueError("No Stripe customer is associated with this API key.")
    url=os.getenv("CUSTOMER_PORTAL_RETURN_URL")
    if not url: raise RuntimeError("Customer portal return URL is not configured.")
    return str(stripe.billing_portal.Session.create(customer=customer,return_url=url).url)
def handle_webhook(payload:bytes,signature:str|None)->dict[str,str]:
    secret=os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret: raise RuntimeError("Stripe webhook signing secret is not configured.")
    if not signature: raise ValueError("Missing Stripe-Signature header.")
    try: event=stripe.Webhook.construct_event(payload,signature,secret)
    except Exception as exc:
        if exc.__class__.__name__=="SignatureVerificationError": raise ValueError("Invalid Stripe webhook signature.") from exc
        raise
    kind,obj=event["type"],event["data"]["object"]
    if kind in {"customer.subscription.updated","customer.subscription.deleted"}:
        meta=obj.get("metadata") or {}; kid,plan=meta.get("api_key_id"),meta.get("plan")
        if kid and plan in PLAN_PRICE_ENV:
            set_subscription(int(kid),plan,str(obj.get("status","canceled")),str(obj.get("customer")) if obj.get("customer") else None,str(obj.get("id")),int(os.getenv(PLAN_LIMIT_ENV[plan],str(PLAN_DEFAULT_LIMIT[plan]))))
        elif obj.get("id"): set_subscription_by_id(str(obj["id"]),str(obj.get("status","canceled")))
    elif kind=="invoice.payment_failed":
        sub_id=obj.get("subscription")
        if sub_id: set_subscription_by_id(str(sub_id),"past_due")
    return {"received":"true","event_type":kind}
