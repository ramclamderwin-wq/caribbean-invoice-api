from __future__ import annotations

import html
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BRAND = "RAMVORA"
PRODUCT = "RAMVORA Invoice Intelligence API"
TAGLINE = "Built for what's next."
TEXT_FOOTER = f"\n\n— {BRAND} · {TAGLINE}"


def _branded_html(heading: str, body_html: str) -> str:
    """Email-safe layout: inline styles, no images or external resources."""
    return (
        '<div style="background:#f4f6f9;padding:32px 16px;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e3e7ee">'
        '<div style="background:#0b1220;padding:20px 28px">'
        f'<span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:0.32em">{BRAND}</span></div>'
        '<div style="padding:28px;color:#1b2533;font-size:15px;line-height:1.6">'
        f'<h1 style="margin:0 0 16px;font-size:20px;color:#0b1220">{html.escape(heading)}</h1>{body_html}</div>'
        '<div style="padding:16px 28px;border-top:1px solid #eef1f5;color:#6b7686;font-size:12px">'
        f'{PRODUCT} · {html.escape(TAGLINE)}</div></div></div>'
    )


def send_api_key_email(recipient: str, api_key: str) -> None:
    """Deliver a newly issued API key using the configured Resend account."""
    api_token = os.getenv("RESEND_API_KEY")
    sender = os.getenv("FROM_EMAIL")
    if not api_token or not sender:
        raise RuntimeError("RESEND_API_KEY and FROM_EMAIL must be configured to deliver customer API keys.")

    safe_key = html.escape(api_key)
    payload = {
        "from": sender,
        "to": [recipient],
        "subject": "Your RAMVORA API key",
        "text": (
            f"Your {PRODUCT} subscription is active.\n\n"
            f"API key: {api_key}\n\n"
            "Store this key securely. You can rotate it from the developer dashboard. "
            "Do not share it or place it in public source code." + TEXT_FOOTER
        ),
        "html": _branded_html(
            "Your subscription is active",
            f"<p>Welcome to the {PRODUCT}.</p>"
            f'<p>Your API key:<br><code style="display:inline-block;margin-top:6px;padding:8px 10px;background:#f4f6f9;border-radius:6px;font-size:14px">{safe_key}</code></p>'
            "<p>Store this key securely. You can rotate it from the developer dashboard. "
            "Do not share it or place it in public source code.</p>",
        ),
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "ramvora-api/0.5",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Email provider returned HTTP {response.status}.")
    except HTTPError as exc:
        raise RuntimeError(f"Email provider rejected the delivery (HTTP {exc.code}).") from exc
    except URLError as exc:
        raise RuntimeError("Email provider could not be reached.") from exc



def send_recovery_code_email(recipient: str, code: str) -> None:
    api_token = os.getenv("RESEND_API_KEY")
    sender = os.getenv("FROM_EMAIL")
    if not api_token or not sender:
        raise RuntimeError("RESEND_API_KEY and FROM_EMAIL must be configured for account recovery.")
    payload = {
        "from": sender,
        "to": [recipient],
        "subject": "Your RAMVORA API key recovery code",
        "text": f"Your one-time recovery code is {code}. It expires in 10 minutes. If you did not request this, ignore this email." + TEXT_FOOTER,
        "html": _branded_html(
            "Your recovery code",
            f'<p>Your one-time recovery code is <strong style="font-size:20px;letter-spacing:0.15em">{html.escape(code)}</strong>.</p>'
            "<p>It expires in 10 minutes. If you did not request this, you can ignore this email.</p>",
        ),
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "ramvora-api/0.5",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Email provider returned HTTP {response.status}.")
    except HTTPError as exc:
        raise RuntimeError(f"Email provider rejected the recovery message (HTTP {exc.code}).") from exc
    except URLError as exc:
        raise RuntimeError("Email provider could not be reached.") from exc
