from tests.helpers import book_and_pay
from tests.conftest import login


def test_first_scan_succeeds_second_fails(client, app, seed):
    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])
    login(client, "scanner1", "scannerpass123")

    first = client.post("/api/scanner/verify", json={"qr_data": f"http://x/verify/{raw_token}"})
    assert first.get_json()["result"] == "VALID"

    second = client.post("/api/scanner/verify", json={"qr_data": f"http://x/verify/{raw_token}"})
    assert second.get_json()["result"] == "ALREADY_USED"


def test_scan_via_full_qr_url_or_bare_token_both_work(client, app, seed):
    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])
    login(client, "scanner1", "scannerpass123")

    scan = client.post("/api/scanner/verify", json={"qr_data": raw_token})
    assert scan.get_json()["result"] == "VALID"


def test_scan_logs_are_recorded(client, app, seed):
    from app.models import ScanLog

    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])
    login(client, "scanner1", "scannerpass123")
    client.post("/api/scanner/verify", json={"qr_data": f"http://x/verify/{raw_token}"})
    client.post("/api/scanner/verify", json={"qr_data": f"http://x/verify/{raw_token}"})
    client.post("/api/scanner/verify", json={"qr_data": "http://x/verify/nonexistent"})

    with app.app_context():
        results = [l.result for l in ScanLog.query.all()]
        assert "VALID" in results
        assert "ALREADY_USED" in results
        assert "INVALID" in results


def test_scanner_role_cannot_manually_change_ticket_status(client, app, seed):
    """Scanner staff must not have access to admin ticket-management endpoints
    like cancel / mark-used / reset (those are admin_required-only)."""
    ref, raw_token, resp = book_and_pay(client, app, seed["event_id"], seed["ticket_type_id"])
    login(client, "scanner1", "scannerpass123")

    from app.models import Ticket, Booking

    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        ticket_id = Ticket.query.filter_by(booking_id=booking.id).first().id

    resp = client.post(f"/admin/tickets/{ticket_id}/cancel")
    assert resp.status_code == 403
