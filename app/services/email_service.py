import logging

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail

logger = logging.getLogger(__name__)


def is_mail_configured() -> bool:
    return bool(current_app.config.get("MAIL_SERVER") and current_app.config.get("MAIL_USERNAME"))


def send_ticket_email(customer, booking, tickets, pdf_bytes_list, event):
    """Sends the digital ticket(s) as PDF attachments plus a secure ticket link.
    Silently skips (logs only) if mail is not configured, so booking flow never
    fails just because email isn't set up yet — matches the requirement to
    prepare the architecture for email delivery without hard-depending on it."""
    if not is_mail_configured():
        logger.info("Mail not configured; skipping ticket email for booking %s", booking.booking_reference)
        return False

    try:
        msg = Message(
            subject=f"Your {event.name} Pass — {booking.booking_reference}",
            recipients=[customer.email],
        )
        base_url = current_app.config["BASE_URL"]
        ticket_links = [f"{base_url}/ticket/{t.secure_slug}" for t in tickets]
        msg.body = render_template(
            "email/ticket_email.txt",
            customer=customer,
            booking=booking,
            tickets=tickets,
            ticket_links=ticket_links,
            event=event,
        )
        for ticket, pdf_bytes in zip(tickets, pdf_bytes_list):
            msg.attach(
                filename=f"{ticket.ticket_id}.pdf",
                content_type="application/pdf",
                data=pdf_bytes,
            )
        mail.send(msg)
        return True
    except Exception:
        logger.exception("Failed to send ticket email for booking %s", booking.booking_reference)
        return False


def send_whatsapp_ticket(customer, booking, tickets, event):
    """Placeholder for WhatsApp delivery (e.g. via WhatsApp Cloud API / Twilio).
    Not implemented — kept as an explicit integration point per the architecture
    requirement. Wire up a provider client here and call it from routes/payment.py
    alongside send_ticket_email()."""
    logger.info(
        "WhatsApp delivery not configured; would send booking %s to %s",
        booking.booking_reference,
        customer.mobile,
    )
    return False
