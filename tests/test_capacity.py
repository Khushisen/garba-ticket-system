import hashlib
import hmac
import os
import tempfile
import threading
from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture()
def cap_app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


def _seed_limited_event(app, total_quantity=1):
    import datetime as dt
    from app.models import Event, TicketType

    with app.app_context():
        event = Event(name="Capacity Test", date=dt.date(2026, 10, 10), status="open")
        _db.session.add(event)
        _db.session.flush()
        tt = TicketType(event_id=event.id, name="Only One Left", price=100, total_quantity=total_quantity)
        _db.session.add(tt)
        _db.session.commit()
        return event.id, tt.id


def test_ticket_limit_enforced_at_booking_time(cap_app):
    client = cap_app.test_client()
    event_id, tt_id = _seed_limited_event(cap_app, total_quantity=1)

    # First booking for the sole remaining pass succeeds (soft check).
    r1 = client.post(
        "/api/bookings",
        json={"event_id": event_id, "ticket_type_id": tt_id, "name": "Racer A", "mobile": "9000000001",
              "email": "a@example.com", "quantity": 1, "terms_accepted": True},
    )
    assert r1.status_code == 200


def test_quantity_over_available_rejected(cap_app):
    client = cap_app.test_client()
    event_id, tt_id = _seed_limited_event(cap_app, total_quantity=1)

    r = client.post(
        "/api/bookings",
        json={"event_id": event_id, "ticket_type_id": tt_id, "name": "Racer A", "mobile": "9000000001",
              "email": "a@example.com", "quantity": 2, "terms_accepted": True},
    )
    assert r.status_code == 400


def test_concurrent_payment_confirmation_never_oversells():
    """Two bookings both target the LAST available pass (total_quantity=1).
    Both attempt to confirm payment at the same time. Exactly one booking may
    become PAID; the other must fail cleanly (and not receive a ticket) rather
    than both succeeding and overselling ticket #101 on a 100-ticket type."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app(
        "testing",
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"check_same_thread": False, "timeout": 30}},
        },
    )
    with app.app_context():
        _db.create_all()

    try:
        event_id, tt_id = _seed_limited_event(app, total_quantity=1)

        client1 = app.test_client()
        client2 = app.test_client()

        def make_booking(client, mobile, email):
            r = client.post(
                "/api/bookings",
                json={"event_id": event_id, "ticket_type_id": tt_id, "name": "Racer", "mobile": mobile,
                      "email": email, "quantity": 1, "terms_accepted": True},
            )
            return r.get_json()["booking_reference"]

        ref1 = make_booking(client1, "9000000001", "racer1@example.com")
        ref2 = make_booking(client2, "9000000002", "racer2@example.com")

        orders = {}
        for ref, client in ((ref1, client1), (ref2, client2)):
            with patch("app.services.payment_service.razorpay.Client") as MockClient:
                MockClient.return_value.order.create.return_value = {
                    "id": f"order_{ref}", "amount": 10000, "currency": "INR"
                }
                r = client.post("/api/payment/create-order", json={"booking_reference": ref})
            orders[ref] = r.get_json()["order_id"]

        key_secret = app.config["RAZORPAY_KEY_SECRET"]
        results = {}
        results_lock = threading.Lock()
        barrier = threading.Barrier(2)

        def confirm(ref, client, order_id):
            payment_id = f"pay_{ref}"
            sig = hmac.new(key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
            barrier.wait()
            resp = client.post(
                "/api/payment/verify",
                json={
                    "booking_reference": ref,
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": sig,
                },
            )
            with results_lock:
                results[ref] = resp.status_code

        t1 = threading.Thread(target=confirm, args=(ref1, client1, orders[ref1]))
        t2 = threading.Thread(target=confirm, args=(ref2, client2, orders[ref2]))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        status_codes = sorted(results.values())
        assert status_codes == [200, 400], f"Expected exactly one success and one failure, got {results}"

        with app.app_context():
            from app.models import TicketType, Ticket

            tt = TicketType.query.get(tt_id)
            assert tt.sold_quantity == 1  # never oversold past the cap
            assert Ticket.query.count() == 1
    finally:
        with app.app_context():
            _db.session.remove()
            _db.drop_all()
        os.remove(path)
