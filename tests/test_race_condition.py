"""
Simulates two gate scanners hitting the SAME ticket's check-in endpoint at
(as close as possible to) the same instant. Required outcome: exactly one
scan gets VALID, the other gets ALREADY_USED — never both VALID.

Uses a real file-backed SQLite database (not :memory:) so that two separate
threads/connections genuinely contend for the same row, the same way two
gate devices would contend over a shared Postgres database in production.
"""

import os
import tempfile
import threading

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture()
def race_app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    application = create_app(
        "testing",
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"check_same_thread": False, "timeout": 30}},
        },
    )
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()
    os.remove(path)


def _seed_one_ticket(app):
    import datetime as dt
    from app.models import Event, TicketType, Customer, Booking, Payment
    from app.models.booking import BOOKING_PAID
    from app.models.payment import PAYMENT_SUCCESS
    from app.services.ticket_service import issue_tickets_for_booking

    with app.app_context():
        event = Event(name="Race Test Event", date=dt.date(2026, 10, 10), status="open")
        _db.session.add(event)
        _db.session.flush()
        tt = TicketType(event_id=event.id, name="General", price=100, total_quantity=5, sold_quantity=1)
        _db.session.add(tt)
        _db.session.flush()

        customer = Customer(name="Race Tester", mobile="9000000000", email="race@example.com")
        _db.session.add(customer)
        _db.session.flush()

        booking = Booking(
            booking_reference="BK-RACE0001",
            event_id=event.id,
            customer_id=customer.id,
            ticket_type_id=tt.id,
            quantity=1,
            amount=100,
            status=BOOKING_PAID,
        )
        _db.session.add(booking)
        _db.session.flush()

        payment = Payment(booking_id=booking.id, amount=100, status=PAYMENT_SUCCESS, razorpay_order_id="order_race")
        _db.session.add(payment)
        _db.session.flush()

        tickets = issue_tickets_for_booking(booking)
        raw_token = tickets[0]._raw_token
        _db.session.commit()
        return raw_token


def test_concurrent_scans_never_both_succeed(race_app):
    raw_token = _seed_one_ticket(race_app)

    from app.services.scan_service import verify_and_checkin

    results = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker(gate_name):
        with race_app.app_context():
            barrier.wait()  # try to make both threads call verify at nearly the same instant
            result, ticket, message = verify_and_checkin(raw_token, gate_name=gate_name)
            with results_lock:
                results.append(result)
            _db.session.remove()  # release this thread's scoped session/connection

    threads = [threading.Thread(target=worker, args=(f"Gate {i}",)) for i in range(1, 3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 2
    assert sorted(results) == ["ALREADY_USED", "VALID"], (
        f"Expected exactly one VALID and one ALREADY_USED, got: {results}"
    )


def test_many_concurrent_scans_of_same_ticket_exactly_one_wins(race_app):
    """Stress version with more concurrent scanners hitting the same ticket."""
    raw_token = _seed_one_ticket(race_app)

    from app.services.scan_service import verify_and_checkin

    N = 8
    results = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(N)

    def worker(i):
        with race_app.app_context():
            barrier.wait()
            result, ticket, message = verify_and_checkin(raw_token, gate_name=f"Gate {i}")
            with results_lock:
                results.append(result)
            _db.session.remove()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert len(results) == N
    assert results.count("VALID") == 1, f"Expected exactly 1 VALID out of {N} concurrent scans, got: {results}"
    assert results.count("ALREADY_USED") == N - 1
