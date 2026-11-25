from __future__ import annotations

import html
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
        "subject": "Your Quillvora API key",
        "text": (
            "Your Quillvora API subscription is active.\n\n"
            f"API key: {api_key}\n\n"
            "Store this key securely. You can rotate it from the developer dashboard. "
            "Do not share it or place it in public source code."
        ),
        "html": (
            "<p>Your Quillvora API subscription is active.</p>"
            f"<p>Your API key: <code>{safe_key}</code></p>"
            "<p>Store this key securely. Do not share it or place it in public source code.</p>"
        ),
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "quillvora-api/0.4",
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
        "subject": "Your Quillvora API key recovery code",
        "text": f"Your one-time recovery code is {code}. It expires in 10 minutes. If you did not request this, ignore this email.",
        "html": f"<p>Your one-time recovery code is <strong>{html.escape(code)}</strong>.</p><p>It expires in 10 minutes. If you did not request this, ignore this email.</p>",
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "quillvora-api/0.4",
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
