import hashlib
import hmac
import json
from unittest.mock import patch

from tests.helpers import book_and_pay
from app.models import Booking, Payment, Ticket
from app.models.booking import BOOKING_PAID, BOOKING_FAILED


def test_full_payment_flow_issues_ticket(client, app, seed):
    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["tickets"]) == 1
    assert raw_token is not None

    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        assert booking.status == BOOKING_PAID
        assert booking.payment.status == "PAYMENT_SUCCESS"
        ticket = Ticket.query.filter_by(booking_id=booking.id).first()
        assert ticket.status == "ACTIVE"


def test_tampered_signature_is_rejected_and_no_ticket_issued(client, app, seed):
    resp = client.post(
        "/api/bookings",
        json={
            "event_id": seed["event_id"],
            "ticket_type_id": seed["ticket_type_id"],
            "name": "Fraud User",
            "mobile": "9999999999",
            "email": "fraud@example.com",
            "quantity": 1,
            "terms_accepted": True,
        },
    )
    ref = resp.get_json()["booking_reference"]

    with patch("app.services.payment_service.razorpay.Client") as MockClient:
        MockClient.return_value.order.create.return_value = {"id": "order_FRAUD", "amount": 10000, "currency": "INR"}
        client.post("/api/payment/create-order", json={"booking_reference": ref})

    verify_resp = client.post(
        "/api/payment/verify",
        json={
            "booking_reference": ref,
            "razorpay_order_id": "order_FRAUD",
            "razorpay_payment_id": "pay_FRAUD",
            "razorpay_signature": "not-a-real-signature",
        },
    )
    assert verify_resp.status_code == 400

    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        assert booking.status == BOOKING_FAILED
        assert Ticket.query.filter_by(booking_id=booking.id).count() == 0


def test_frontend_success_page_alone_never_issues_ticket(client, app, seed):
    """A booking that never went through create-order/verify (i.e. only the
    user 'returning to a success page') must never have a ticket."""
    resp = client.post(
        "/api/bookings",
        json={
            "event_id": seed["event_id"],
            "ticket_type_id": seed["ticket_type_id"],
            "name": "No Payment",
            "mobile": "9999999998",
            "email": "nopay@example.com",
            "quantity": 1,
            "terms_accepted": True,
        },
    )
    ref = resp.get_json()["booking_reference"]
    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        assert Ticket.query.filter_by(booking_id=booking.id).count() == 0


def test_duplicate_verify_call_is_idempotent(client, app, seed):
    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])
    first_ticket_id = resp.get_json()["tickets"][0]["ticket_id"]

    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        order_id = booking.payment.razorpay_order_id
        payment_id = booking.payment.razorpay_payment_id
        signature = booking.payment.razorpay_signature

    # Call verify again with the same (now-already-processed) payment details.
    resp2 = client.post(
        "/api/payment/verify",
        json={
            "booking_reference": ref,
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
    )
    assert resp2.status_code == 200
    assert resp2.get_json()["tickets"][0]["ticket_id"] == first_ticket_id

    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        assert Ticket.query.filter_by(booking_id=booking.id).count() == 1  # not duplicated


def test_webhook_rejects_bad_signature(client, app, seed):
    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"order_id": "order_X", "id": "pay_X"}}},
    }
    resp = client.post(
        "/api/payment/webhook",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "bad-sig"},
    )
    assert resp.status_code == 400


def test_webhook_captures_payment_with_valid_signature(client, app, seed):
    resp = client.post(
        "/api/bookings",
        json={
            "event_id": seed["event_id"],
            "ticket_type_id": seed["ticket_type_id"],
            "name": "Webhook User",
            "mobile": "9999999997",
            "email": "webhook@example.com",
            "quantity": 1,
            "terms_accepted": True,
        },
    )
    ref = resp.get_json()["booking_reference"]

    with patch("app.services.payment_service.razorpay.Client") as MockClient:
        MockClient.return_value.order.create.return_value = {"id": "order_WH1", "amount": 10000, "currency": "INR"}
        client.post("/api/payment/create-order", json={"booking_reference": ref})

    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"order_id": "order_WH1", "id": "pay_WH1"}}},
    }
    raw_body = json.dumps(payload).encode()
    webhook_secret = app.config["RAZORPAY_WEBHOOK_SECRET"]
    signature = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()

    resp = client.post(
        "/api/payment/webhook",
        data=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    assert resp.status_code == 200

    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        assert booking.status == BOOKING_PAID
        assert Ticket.query.filter_by(booking_id=booking.id).count() == 1

    # Duplicate webhook delivery must not create a second ticket.
    resp2 = client.post(
        "/api/payment/webhook",
        data=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    assert resp2.status_code == 200
    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        assert Ticket.query.filter_by(booking_id=booking.id).count() == 1
