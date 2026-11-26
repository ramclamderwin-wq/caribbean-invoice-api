"""Client-address resolution behind proxies (Render has two proxy layers)."""
from types import SimpleNamespace

import pytest

from app.net import client_ip


def _request(xff: str | None, peer: str = "10.0.0.9"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


@pytest.mark.parametrize("hops, xff, expected", [
    # Render: client -> edge proxy -> load balancer -> app. The edge appends the real
    # client, the balancer appends the edge, so the client is the 2nd entry from the right.
    ("2", "203.0.113.7, 10.1.2.3", "203.0.113.7"),
    # A forged left-most entry is ignored.
    ("2", "1.2.3.4, 203.0.113.7, 10.1.2.3", "203.0.113.7"),
    # Single reverse proxy.
    ("1", "1.2.3.4, 203.0.113.7", "203.0.113.7"),
    # No proxy in front: use the socket peer, never the header.
    ("0", "1.2.3.4", "10.0.0.9"),
    # Too few entries or garbage: fall back to the socket peer.
    ("2", "203.0.113.7", "10.0.0.9"),
    ("2", "not-an-ip, 10.1.2.3", "10.0.0.9"),
])
def test_client_ip_counts_trusted_hops_from_the_right(monkeypatch, hops, xff, expected):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", hops)
    assert client_ip(_request(xff)) == expected


def test_render_blueprint_uses_two_proxy_hops():
    text = open("render.yaml", encoding="utf-8").read()
    assert 'key: TRUSTED_PROXY_HOPS\n        value: "2"' in text
