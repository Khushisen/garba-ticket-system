"""
Entry-gate scan verification.

The core correctness requirement: a ticket must transition ACTIVE -> USED
atomically, so that two simultaneous scans of the same QR can never both
succeed. See verify_and_checkin() for the atomic compare-and-swap UPDATE
that guarantees this across SQLite, Postgres, and MySQL alike.
"""

import datetime as dt

from sqlalchemy import update

from app.extensions import db
from app.models import Ticket, Booking, Payment, ScanLog
from app.models.ticket import (
    TICKET_ACTIVE,
    TICKET_USED,
    TICKET_CANCELLED,
    TICKET_REFUNDED,
    TICKET_EXPIRED,
)
from app.models.payment import PAYMENT_SUCCESS
from app.services.qr_service import hash_token

RESULT_VALID = "VALID"
RESULT_ALREADY_USED = "ALREADY_USED"
RESULT_INVALID = "INVALID"
RESULT_CANCELLED = "CANCELLED"
RESULT_REFUNDED = "REFUNDED"
RESULT_EXPIRED = "EXPIRED"
RESULT_PAYMENT_NOT_CONFIRMED = "PAYMENT_NOT_CONFIRMED"


def verify_and_checkin(raw_token: str, scanner_user=None, gate_name=None, device_info=None, ip_address=None):
    """
    Returns (result_code: str, ticket_or_none: Ticket, message: str)

    Concurrency design: rather than relying on SELECT ... FOR UPDATE (whose
    locking semantics vary by database — SQLite in particular does not honor
    it), the ACTIVE -> USED transition is done as a single atomic
    UPDATE ... WHERE status = 'ACTIVE' compare-and-swap. The database engine
    guarantees only one concurrent UPDATE can win that WHERE clause; every
    other concurrent caller's UPDATE affects zero rows, so they fall through
    to the "already handled" path. This gives the same one-writer-wins
    guarantee on SQLite, Postgres, and MySQL alike.
    """
    token_hash = hash_token(raw_token) if raw_token else None

    if not token_hash:
        _log_scan(None, token_hash, scanner_user, gate_name, device_info, ip_address, RESULT_INVALID)
        db.session.commit()
        return RESULT_INVALID, None, "This QR code is not registered."

    ticket = Ticket.query.filter_by(qr_token_hash=token_hash).first()

    if ticket is None:
        _log_scan(None, token_hash, scanner_user, gate_name, device_info, ip_address, RESULT_INVALID)
        db.session.commit()
        return RESULT_INVALID, None, "This QR code is not registered."

    booking = ticket.booking
    payment = booking.payment if booking else None

    if payment is None or payment.status != PAYMENT_SUCCESS:
        _log_scan(ticket, token_hash, scanner_user, gate_name, device_info, ip_address, RESULT_PAYMENT_NOT_CONFIRMED)
        db.session.commit()
        return RESULT_PAYMENT_NOT_CONFIRMED, ticket, "Payment for this ticket was never confirmed."

    # ---- Attempt the atomic ACTIVE -> USED compare-and-swap ----
    used_by = (scanner_user.username if scanner_user else None) or gate_name
    now = dt.datetime.utcnow()

    stmt = (
        update(Ticket)
        .where(Ticket.id == ticket.id, Ticket.status == TICKET_ACTIVE)
        .values(status=TICKET_USED, used_at=now, used_by=used_by)
    )
    result = db.session.execute(stmt)

    if result.rowcount == 1:
        # We won the race — this call (and only this call) transitioned the ticket.
        db.session.refresh(ticket)
        _log_scan(ticket, token_hash, scanner_user, gate_name, device_info, ip_address, RESULT_VALID)
        db.session.commit()
        return RESULT_VALID, ticket, "Entry allowed."

    # rowcount == 0: someone else's status (or a concurrent winner) beat us here.
    # Re-read the current, authoritative status to report the right reason.
    db.session.rollback()  # discard our no-op update attempt, get a fresh read
    ticket = Ticket.query.filter_by(qr_token_hash=token_hash).first()

    status_to_result = {
        TICKET_USED: RESULT_ALREADY_USED,
        TICKET_CANCELLED: RESULT_CANCELLED,
        TICKET_REFUNDED: RESULT_REFUNDED,
        TICKET_EXPIRED: RESULT_EXPIRED,
    }
    result_code = status_to_result.get(ticket.status, RESULT_INVALID)
    message = {
        RESULT_ALREADY_USED: f"Ticket already used at {ticket.used_at}.",
        RESULT_CANCELLED: "This ticket was cancelled.",
        RESULT_REFUNDED: "This ticket was refunded.",
        RESULT_EXPIRED: "This ticket has expired.",
    }.get(result_code, "Ticket status is invalid.")

    _log_scan(ticket, token_hash, scanner_user, gate_name, device_info, ip_address, result_code)
    db.session.commit()
    return result_code, ticket, message


def _log_scan(ticket, token_hash, scanner_user, gate_name, device_info, ip_address, result):
    log = ScanLog(
        ticket_id=ticket.id if ticket else None,
        scanned_token_hash=token_hash,
        scanner_user_id=scanner_user.id if scanner_user else None,
        gate_name=gate_name,
        result=result,
        device_information=device_info,
        ip_address=ip_address,
    )
    db.session.add(log)

