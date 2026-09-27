import logging

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.models import Booking
from app.models.booking import BOOKING_PENDING
from app.services.payment_service import (
    create_order_for_booking,
    verify_and_mark_paid,
    verify_webhook_signature,
    handle_webhook_payment_captured,
    handle_webhook_payment_failed,
    PaymentVerificationError,
)
from app.services.ticket_delivery import deliver_tickets_for_booking

payment_bp = Blueprint("payment_api", __name__)
logger = logging.getLogger(__name__)


@payment_bp.route("/create-order", methods=["POST"])
@limiter.limit("20 per minute")
def create_order():
    data = request.get_json(silent=True) or {}
    reference = data.get("booking_reference")
    booking = Booking.query.filter_by(booking_reference=reference).first()
    if booking is None:
        return jsonify({"success": False, "error": "Booking not found."}), 404
    if booking.status != BOOKING_PENDING:
        return jsonify({"success": False, "error": f"Booking is not payable (status: {booking.status})."}), 400

    order = create_order_for_booking(booking)
    return jsonify(
        {
            "success": True,
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": current_app.config["RAZORPAY_KEY_ID"],
            "booking_reference": booking.booking_reference,
            "customer_name": booking.customer.name,
            "customer_email": booking.customer.email,
            "customer_mobile": booking.customer.mobile,
        }
    )


@payment_bp.route("/verify", methods=["POST"])
@limiter.limit("20 per minute")
def verify_payment():
    """Called from the Razorpay Checkout success handler on the frontend.
    NEVER trusted by itself — verify_and_mark_paid() re-checks the HMAC
    signature server-side before any ticket is issued."""
    data = request.get_json(silent=True) or {}
    reference = data.get("booking_reference")
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")

    booking = Booking.query.filter_by(booking_reference=reference).first()
    if booking is None:
        return jsonify({"success": False, "error": "Booking not found."}), 404

    try:
        tickets = verify_and_mark_paid(booking, razorpay_order_id, razorpay_payment_id, razorpay_signature)
    except PaymentVerificationError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    deliver_tickets_for_booking(booking, tickets)

    return jsonify(
        {
            "success": True,
            "booking_reference": booking.booking_reference,
            "tickets": [{"ticket_id": t.ticket_id, "view_url": f"/ticket/{t.secure_slug}"} for t in tickets],
        }
    )


@payment_bp.route("/webhook", methods=["POST"])
def webhook():
    """Razorpay server-to-server webhook. Exempted from CSRF (see app/__init__.py)
    because it isn't a browser form post; authenticity instead comes from the
    HMAC signature check below, which is the stronger guarantee here."""
    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_webhook_signature(raw_body, signature):
        logger.warning("Webhook signature verification failed")
        return jsonify({"error": "invalid signature"}), 400

    payload = request.get_json(silent=True) or {}
    event_type = payload.get("event")
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    payment_id = entity.get("id")

    if event_type == "payment.captured" and order_id and payment_id:
        booking_and_tickets = handle_webhook_payment_captured(order_id, payment_id, payload)
        if booking_and_tickets:
            from app.models import Payment

            payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
            if payment:
                deliver_tickets_for_booking(payment.booking, booking_and_tickets)
    elif event_type in ("payment.failed",) and order_id:
        handle_webhook_payment_failed(order_id)
    else:
        logger.info("Unhandled webhook event type: %s", event_type)

    # Always 200 quickly so Razorpay doesn't retry-storm us once we've processed
    # (or intentionally ignored) the event.
    return jsonify({"status": "ok"}), 200
