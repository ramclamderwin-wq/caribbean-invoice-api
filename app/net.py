"""Client address resolution for rate limiting and audit.

Uvicorn runs with ``--forwarded-allow-ips '*'`` so that HTTPS is detected behind
Render's proxy. With that setting Uvicorn reports the *left-most*
X-Forwarded-For entry as the client, and that entry is whatever the caller sent.
Using it for throttling would let anyone bypass per-IP limits with a forged
header.

Instead, count ``TRUSTED_PROXY_HOPS`` entries from the *right*: each trusted
proxy appends the address it received the connection from, so the entry that
the nearest trusted proxy appended cannot be forged by the client. Render has
two proxy layers in front of the app, so set ``TRUSTED_PROXY_HOPS=2`` there
(verified on staging); the code default of 1 suits a single reverse proxy. Set 0 when the app is
reached directly (no proxy); then the socket peer address is used.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os

from fastapi import Request


def _trusted_hops() -> int:
    try:
        return max(0, int(os.getenv("TRUSTED_PROXY_HOPS", "1")))
    except ValueError:
        return 1


def client_ip(request: Request) -> str:
    hops = _trusted_hops()
    if hops:
        forwarded = request.headers.get("x-forwarded-for", "")
        entries = [item.strip() for item in forwarded.split(",") if item.strip()]
        if len(entries) >= hops:
            candidate = entries[-hops]
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass  # malformed entry: fall back to the transport address
    # No usable forwarded entry: use the connection's peer address.
    return request.client.host if request.client else "unknown"


def client_fingerprint(request: Request) -> str:
    """Stable, non-reversible identifier for audit logs (no raw IP stored)."""
    salt = os.getenv("API_KEY_ENCRYPTION_KEY", "") or os.getenv("API_ADMIN_KEY", "")
    return hashlib.sha256((salt + "|" + client_ip(request)).encode("utf-8")).hexdigest()[:16]
