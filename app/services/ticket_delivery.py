import os
import logging

from flask import current_app

from app.services.pdf_service import build_ticket_pdf
from app.services.qr_service import generate_qr_png_bytes, build_qr_payload_url
from app.services.email_service import send_ticket_email
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)


def _raw_token_for(ticket: Ticket) -> str | None:
    """Raw token is only available as a transient in-memory attribute set at
    issuance time (issue_tickets_for_booking). If a ticket object was reloaded
    fresh from the DB (e.g. re-downloading a PDF later), the raw token cannot
    be recovered — that's by design, since only the hash is stored. Callers
    needing to regenerate a PDF later must re-issue via a signed reset flow,
    not by reading the raw token back out."""
    return getattr(ticket, "_raw_token", None)


def build_and_store_ticket_pdf(ticket: Ticket, booking, event) -> bytes | None:
    raw_token = _raw_token_for(ticket)
    if raw_token is None:
        return None

    pdf_bytes = build_ticket_pdf(ticket, booking, event, raw_token, current_app.config["BASE_URL"])
    out_dir = current_app.config["TICKET_PDF_DIR"]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{ticket.ticket_id}.pdf")
    with open(path, "wb") as f:
        f.write(pdf_bytes)

    # Also cache a standalone QR PNG so the web ticket page can display it without
    # ever needing to read the raw token back out of the database (it isn't stored
    # there at all — only its SHA-256 hash is, see qr_service.py).
    qr_url = build_qr_payload_url(current_app.config["BASE_URL"], raw_token)
    qr_bytes = generate_qr_png_bytes(qr_url)
    qr_dir = current_app.config["TICKET_QR_DIR"]
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"{ticket.secure_slug}.png")
    with open(qr_path, "wb") as f:
        f.write(qr_bytes)

    return pdf_bytes


def deliver_tickets_for_booking(booking, tickets):
    """Generates PDFs for freshly-issued tickets (those with a live raw token)
    and attempts email delivery. Safe to call multiple times (idempotent webhook
    + frontend-callback paths) — tickets without a live raw token are skipped."""
    event = booking.event
    pdf_bytes_list = []
    fresh_tickets = []
    for ticket in tickets:
        pdf_bytes = build_and_store_ticket_pdf(ticket, booking, event)
        if pdf_bytes is not None:
            pdf_bytes_list.append(pdf_bytes)
            fresh_tickets.append(ticket)

    if fresh_tickets:
        try:
            send_ticket_email(booking.customer, booking, fresh_tickets, pdf_bytes_list, event)
        except Exception:
            logger.exception("Ticket email delivery failed for booking %s", booking.booking_reference)
