from tests.helpers import book_and_pay
from app.models import Ticket
from app.models.ticket import TICKET_CANCELLED, TICKET_REFUNDED


def test_ticket_ids_and_qr_hashes_are_unique(client, app, seed):
    ref1, token1, _ = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"], email="a@example.com", mobile="9000000001")
    ref2, token2, _ = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"], email="b@example.com", mobile="9000000002")

    assert token1 != token2

    with app.app_context():
        tickets = Ticket.query.all()
        ticket_ids = [t.ticket_id for t in tickets]
        hashes = [t.qr_token_hash for t in tickets]
        slugs = [t.secure_slug for t in tickets]
        assert len(ticket_ids) == len(set(ticket_ids))
        assert len(hashes) == len(set(hashes))
        assert len(slugs) == len(set(slugs))
        # ticket id follows the documented pattern
        for tid in ticket_ids:
            assert tid.startswith("GARBA26-")


def test_qr_token_is_not_predictable(app, seed):
    from app.services.qr_service import generate_raw_token

    tokens = {generate_raw_token() for _ in range(50)}
    assert len(tokens) == 50  # no collisions
    for t in tokens:
        assert len(t) >= 32  # sufficiently long


def test_scanning_invalid_qr_fails(client, app, seed):
    from tests.conftest import login

    login(client, "scanner1", "scannerpass123")
    resp = client.post("/api/scanner/verify", json={"qr_data": "http://x/verify/totally-made-up-token"})
    assert resp.status_code == 200
    assert resp.get_json()["result"] == "INVALID"


def test_scanning_cancelled_ticket_is_denied(client, app, seed):
    from tests.conftest import login
    from app.extensions import db

    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])

    with app.app_context():
        from app.models import Booking

        booking = Booking.query.filter_by(booking_reference=ref).first()
        ticket = Ticket.query.filter_by(booking_id=booking.id).first()
        ticket.status = TICKET_CANCELLED
        db.session.commit()

    login(client, "scanner1", "scannerpass123")
    scan_resp = client.post("/api/scanner/verify", json={"qr_data": f"http://x/verify/{raw_token}"})
    assert scan_resp.get_json()["result"] == "CANCELLED"


def test_scanning_refunded_ticket_is_denied(client, app, seed):
    from tests.conftest import login
    from app.extensions import db
    from app.models import Booking

    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])
    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        ticket = Ticket.query.filter_by(booking_id=booking.id).first()
        ticket.status = TICKET_REFUNDED
        db.session.commit()

    login(client, "scanner1", "scannerpass123")
    scan_resp = client.post("/api/scanner/verify", json={"qr_data": f"http://x/verify/{raw_token}"})
    assert scan_resp.get_json()["result"] == "REFUNDED"
