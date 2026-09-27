import os

from flask import Blueprint, render_template, send_file, abort, current_app
from flask_login import current_user

from app.models import Ticket
from app.models.payment import PAYMENT_SUCCESS
from app.services.scan_service import verify_and_checkin

ticket_bp = Blueprint("ticket", __name__)


@ticket_bp.route("/ticket/<secure_slug>")
def view_ticket(secure_slug):
    ticket = Ticket.query.filter_by(secure_slug=secure_slug).first_or_404()
    booking = ticket.booking
    payment = booking.payment
    payment_confirmed = bool(payment and payment.status == PAYMENT_SUCCESS)
    return render_template(
        "public/ticket_view.html",
        ticket=ticket,
        booking=booking,
        event=booking.event,
        payment_confirmed=payment_confirmed,
    )


@ticket_bp.route("/ticket/<secure_slug>/download")
def download_ticket(secure_slug):
    ticket = Ticket.query.filter_by(secure_slug=secure_slug).first_or_404()
    path = os.path.join(current_app.config["TICKET_PDF_DIR"], f"{ticket.ticket_id}.pdf")
    if not os.path.exists(path):
        abort(404, description="PDF not available yet — please refresh in a moment or contact support.")
    return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=f"{ticket.ticket_id}.pdf")


@ticket_bp.route("/ticket/<secure_slug>/qr.png")
def qr_image(secure_slug):
    ticket = Ticket.query.filter_by(secure_slug=secure_slug).first_or_404()
    path = os.path.join(current_app.config["TICKET_QR_DIR"], f"{ticket.secure_slug}.png")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/png")


@ticket_bp.route("/verify/<raw_token>")
def verify_landing(raw_token):
    """
    QR payloads point here. Two behaviors:
    - Logged in as scanner/admin staff: perform the real atomic check-in immediately.
    - Anyone else (e.g. a customer curious about their own QR): show a generic
      informational page only, WITHOUT performing check-in, so opening/forwarding
      a ticket link never accidentally burns the entry.
    """
    if current_user.is_authenticated and (current_user.is_admin or current_user.is_scanner):
        result, ticket, message = verify_and_checkin(
            raw_token,
            scanner_user=current_user,
            gate_name=current_user.gate_name,
            device_info="web-link",
        )
        return render_template("scanner/result.html", result=result, ticket=ticket, message=message)

    return render_template("public/verify_info.html")
