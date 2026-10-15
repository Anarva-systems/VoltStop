import hashlib
import hmac
from types import SimpleNamespace
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from app.auth.dependencies import AuthenticatedUser
from app.core.config import Settings
from app.core.errors import ApiError
from app.payments.router import verify_razorpay_checkout
from app.payments.schemas import RazorpayCheckoutVerification
from app.payments.service import RazorpayGateway, verify_checkout_signature
from starlette.requests import Request


SECRET = "synthetic-test-secret-for-checkout-verification"
USER = AuthenticatedUser(id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))


def run_coroutine(coroutine):
    """Run these deterministic test coroutines without opening Windows event-loop sockets."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("Test coroutine unexpectedly suspended on external work")


def _signature(order_id="order_test_123", payment_id="pay_test_456"):
    return hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def _settings(**overrides):
    values = {
        "environment": "development",
        "razorpay_mode": "test",
        "razorpay_key_id": "rzp_test_checkout_fixture",
        "razorpay_key_secret": SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class FakeDatabase:
    def __init__(self, *, owns_order=True):
        self.owns_order = owns_order
        self.pool = object()
        self.processed = []
        self.provider_calls = []

    async def user_owns_payment_order(self, order_id, user_id):
        return self.owns_order and user_id == USER.id and order_id == "order_test_123"

    async def process_payment_webhook(self, *args):
        self.processed.append(args)
        return True


class FakeHttpClient:
    def __init__(self, payment=None, order=None):
        self.payment = payment
        self.order = order
        self.requests = []

    async def get(self, url, *, auth):
        self.requests.append((url, auth))
        return httpx.Response(200, json=self.payment)

    async def post(self, url, *, auth, json):
        self.requests.append((url, auth, json))
        return httpx.Response(200, json=self.order)


def _request(client):
    app = SimpleNamespace(state=SimpleNamespace(http_client=client))
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "app": app})


def test_checkout_signature_uses_order_and_payment_id_and_rejects_tampering():
    signature = _signature()
    assert verify_checkout_signature("order_test_123", "pay_test_456", signature, SECRET)
    assert not verify_checkout_signature("order_other", "pay_test_456", signature, SECRET)
    assert not verify_checkout_signature("order_test_123", "pay_test_456", signature, "")
    assert not verify_checkout_signature("order_test_123", "pay_test_456", None, SECRET)


def test_gateway_reads_provider_payment_and_requires_matching_test_mode():
    payment_fixture = {
            "id": "pay_test_456", "order_id": "order_test_123", "amount": 35000,
            "currency": "INR", "status": "captured",
        }
    client = FakeHttpClient(payment_fixture)
    payment = run_coroutine(RazorpayGateway(client, _settings()).fetch_payment("pay_test_456"))
    assert payment["status"] == "captured"
    assert client.requests == [(
        "https://api.razorpay.com/v1/payments/pay_test_456",
        ("rzp_test_checkout_fixture", SECRET),
    )]

    mismatch_client = FakeHttpClient(payment_fixture)
    with pytest.raises(ApiError) as error:
        run_coroutine(RazorpayGateway(mismatch_client, SimpleNamespace(
            razorpay_mode="unconfigured",
            razorpay_key_id="rzp_test_checkout_fixture",
            razorpay_key_secret=SECRET,
        )).fetch_payment("pay_test_456"))
    assert error.value.detail["code"] == "PAYMENT_MODE_UNCONFIGURED"
    assert mismatch_client.requests == []


def test_gateway_creates_server_order_with_test_credentials_and_minor_units():
    client = FakeHttpClient(order={"id": "order_test_123", "amount": 35050, "currency": "INR"})
    result = run_coroutine(
        RazorpayGateway(client, _settings()).create_order(
            UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"), Decimal("350.50")
        )
    )
    assert result == {
        "order_id": "order_test_123",
        "amount_paise": 35050,
        "currency": "INR",
        "key_id": "rzp_test_checkout_fixture",
    }
    assert client.requests[0][0:2] == (
        "https://api.razorpay.com/v1/orders",
        ("rzp_test_checkout_fixture", SECRET),
    )
    assert client.requests[0][2]["amount"] == 35050
    assert client.requests[0][2]["currency"] == "INR"


def test_checkout_callback_verifies_owner_signature_provider_and_reconciles_capture():
    client = FakeHttpClient({
            "id": "pay_test_456", "order_id": "order_test_123", "amount": 35000,
            "currency": "INR", "status": "captured",
        })
    database = FakeDatabase()
    result = run_coroutine(verify_razorpay_checkout(
        RazorpayCheckoutVerification(
            order_id="order_test_123", payment_id="pay_test_456", signature=_signature()
        ),
        _request(client), USER, database, _settings(),
    ))
    assert result["data"] == {"verified": True, "status": "captured"}
    assert database.processed == [("order_test_123", "pay_test_456", 35000, "INR", True)]
    assert len(client.requests) == 1


def test_invalid_signature_is_rejected_before_provider_or_database_mutation():
    client = FakeHttpClient({})
    database = FakeDatabase()
    with pytest.raises(ApiError) as error:
        run_coroutine(verify_razorpay_checkout(
            RazorpayCheckoutVerification(
                order_id="order_test_123", payment_id="pay_test_456", signature="0" * 64
            ),
            _request(client), USER, database, _settings(),
        ))
    assert error.value.detail["code"] == "INVALID_PAYMENT_SIGNATURE"
    assert client.requests == []
    assert database.processed == []


def test_order_owner_is_checked_before_asking_provider():
    client = FakeHttpClient({})
    database = FakeDatabase(owns_order=False)
    with pytest.raises(ApiError) as error:
        run_coroutine(verify_razorpay_checkout(
            RazorpayCheckoutVerification(
                order_id="order_test_123", payment_id="pay_test_456", signature=_signature()
            ),
            _request(client), USER, database, _settings(),
        ))
    assert error.value.status_code == 404
    assert client.requests == []
    assert database.processed == []


def test_uncaptured_provider_payment_stays_pending_and_is_not_marked_paid():
    client = FakeHttpClient({
            "id": "pay_test_456", "order_id": "order_test_123", "amount": 35000,
            "currency": "INR", "status": "authorized",
        })
    database = FakeDatabase()
    result = run_coroutine(verify_razorpay_checkout(
        RazorpayCheckoutVerification(
            order_id="order_test_123", payment_id="pay_test_456", signature=_signature()
        ),
        _request(client), USER, database, _settings(),
    ))
    assert result["data"] == {"verified": False, "status": "authorized"}
    assert database.processed == []
