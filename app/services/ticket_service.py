import datetime as dt
import secrets
import string

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Ticket, Booking
from app.models.ticket import TICKET_ACTIVE
from app.services.qr_service import generate_raw_token, generate_secure_slug, hash_token

ALPHABET = string.ascii_uppercase + string.digits


def _random_suffix(n=7):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def _generate_unique_ticket_id(event_year: int) -> str:
    for _ in range(20):
        candidate = f"GARBA{event_year % 100:02d}-{_random_suffix()}"
        if not Ticket.query.filter_by(ticket_id=candidate).first():
            return candidate
    raise RuntimeError("Could not generate a unique ticket ID after multiple attempts")


def issue_tickets_for_booking(booking: Booking) -> list[Ticket]:
    """
    Create one Ticket row per quantity purchased on a PAID booking.
    Must only ever be called after payment has been independently verified
    (see payment_service.verify_and_mark_paid). Idempotent: if tickets already
    exist for this booking, returns them unchanged instead of duplicating.
    """
    existing = Ticket.query.filter_by(booking_id=booking.id).all()
    if existing:
        return existing

    event_year = booking.event.date.year if booking.event and booking.event.date else dt.datetime.utcnow().year
    mobile_last4 = (booking.customer.mobile or "")[-4:] if booking.customer else None

    tickets = []
    for _ in range(booking.quantity):
        raw_token = generate_raw_token()
        token_hash = hash_token(raw_token)
        secure_slug = generate_secure_slug()

        ticket = Ticket(
            booking_id=booking.id,
            ticket_id=_generate_unique_ticket_id(event_year),
            qr_token_hash=token_hash,
            secure_slug=secure_slug,
            holder_name=booking.customer.name if booking.customer else "Guest",
            ticket_type_name=booking.ticket_type.name if booking.ticket_type else "General",
            mobile_last4=mobile_last4,
            status=TICKET_ACTIVE,
        )
        # Stash the raw token as a transient attribute (never persisted) so the
        # caller can build the QR image / PDF / email immediately after issuing.
        ticket._raw_token = raw_token
        db.session.add(ticket)
        tickets.append(ticket)

    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise

    return tickets
