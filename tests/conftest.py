"""Test adapter for StripeClient calls, retaining resource-level mocks in tests."""
from types import SimpleNamespace

import pytest
import stripe


class _Service:
    def __init__(self, resource):
        self._resource = resource

    def create(self, params=None):
        return self._resource.create(**(params or {}))

    def retrieve(self, resource_id):
        return self._resource.retrieve(resource_id)

    def list(self, params=None):
        return self._resource.list(**(params or {}))

    def cancel(self, resource_id):
        return self._resource.cancel(resource_id)


@pytest.fixture(autouse=True)
def stripe_client_test_adapter(monkeypatch):
    """Bridge StripeClient service calls to the existing isolated SDK mocks."""
    class FakeStripeClient:
        def __init__(self, secret, **kwargs):
            self.v1 = SimpleNamespace(
                checkout=SimpleNamespace(sessions=_Service(stripe.checkout.Session)),
                subscriptions=_Service(stripe.Subscription),
                customers=_Service(stripe.Customer),
                charges=_Service(stripe.Charge),
                billing_portal=SimpleNamespace(sessions=_Service(stripe.billing_portal.Session)),
            )

        def construct_event(self, payload, signature, secret):
            return stripe.Webhook.construct_event(payload, signature, secret)

    monkeypatch.setattr(stripe, "StripeClient", FakeStripeClient)
