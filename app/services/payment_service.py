"""
Payment lifecycle.

CRITICAL RULE: a ticket is only ever issued from verify_and_mark_paid() /
handle_webhook_payment_captured(), both of which require an independently
verified Razorpay signature. The frontend "payment success" callback alone
is NEVER sufficient — see routes/payment.py for how the two paths combine.
"""

import hashlib
import hmac
import logging

import razorpay
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Booking, Payment, TicketType
from app.models.booking import BOOKING_PAID, BOOKING_FAILED, BOOKING_CANCELLED
from app.models.payment import (
    PAYMENT_PENDING,
    PAYMENT_SUCCESS,
    PAYMENT_FAILED,
)
from app.services.ticket_service import issue_tickets_for_booking

logger = logging.getLogger(__name__)


class PaymentVerificationError(Exception):
    pass


def get_client() -> razorpay.Client:
    key_id = current_app.config["RAZORPAY_KEY_ID"]
    key_secret = current_app.config["RAZORPAY_KEY_SECRET"]
    return razorpay.Client(auth=(key_id, key_secret))


def create_order_for_booking(booking: Booking) -> dict:
    """Create a Razorpay order server-side. Amount is taken from our own DB
    (booking.amount), never trusted from the client, so a tampered frontend
    price cannot change what is actually charged."""
    client = get_client()
    amount_paise = int(round(float(booking.amount) * 100))

    order = client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": booking.booking_reference,
            "notes": {
                "booking_reference": booking.booking_reference,
                "booking_id": str(booking.id),
            },
        }
    )

    payment = booking.payment
    if payment is None:
        payment = Payment(booking_id=booking.id, amount=booking.amount, status=PAYMENT_PENDING)
        db.session.add(payment)
    payment.razorpay_order_id = order["id"]
    payment.status = PAYMENT_PENDING
    db.session.commit()

    return order


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Independently verify the payment using Razorpay's HMAC-SHA256 signature
    scheme: signature = HMAC_SHA256(order_id + '|' + payment_id, key_secret).
    This is the mandatory backend check — never trust the frontend alone."""
    key_secret = current_app.config["RAZORPAY_KEY_SECRET"]
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(key_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool:
    webhook_secret = current_app.config["RAZORPAY_WEBHOOK_SECRET"]
    expected = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_signature or "")


def _reserve_stock_or_raise(booking: Booking):
    """Atomically increment sold_quantity, preventing overselling under concurrency.

    Uses a single compare-and-swap UPDATE (sold_quantity = sold_quantity + qty
    WHERE total_quantity - sold_quantity >= qty) rather than SELECT ... FOR
    UPDATE, whose locking semantics are unreliable on SQLite. A plain atomic
    UPDATE with the capacity check in its WHERE clause gives the same
    no-lost-update guarantee on SQLite, Postgres, and MySQL alike: the
    database itself only ever lets one concurrent writer's UPDATE match and
    succeed once capacity is exhausted."""
    from sqlalchemy import update as sa_update

    stmt = (
        sa_update(TicketType)
        .where(
            TicketType.id == booking.ticket_type_id,
            (TicketType.total_quantity - TicketType.sold_quantity) >= booking.quantity,
        )
        .values(sold_quantity=TicketType.sold_quantity + booking.quantity)
    )
    result = db.session.execute(stmt)
    if result.rowcount != 1:
        raise PaymentVerificationError(
            "Not enough tickets remaining for this pass type — refund required."
        )


def verify_and_mark_paid(booking: Booking, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str):
    """
    Called from the frontend "payment success" callback route.
    Steps (all required — this is the core security-critical function):
      1. Verify the booking actually has a matching, still-pending payment record.
      2. Verify the Razorpay order id matches the one WE created for this booking.
      3. Verify the HMAC signature server-side.
      4. Only then: mark payment SUCCESS, atomically reserve stock, and issue tickets.
    Idempotent: if the booking is already PAID, does nothing further (guards against
    duplicate calls / the webhook and the frontend callback both firing).
    """
    payment = booking.payment
    if payment is None:
        raise PaymentVerificationError("No payment record found for this booking.")

    if booking.status == BOOKING_PAID and payment.status == PAYMENT_SUCCESS:
        # Already processed (e.g. webhook got there first) — idempotent no-op.
        return issue_tickets_for_booking(booking)

    if payment.razorpay_order_id != razorpay_order_id:
        raise PaymentVerificationError("Order ID mismatch.")

    if not verify_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        payment.status = PAYMENT_FAILED
        payment.failure_reason = "Signature verification failed"
        booking.status = BOOKING_FAILED
        db.session.commit()
        raise PaymentVerificationError("Payment signature verification failed.")

    try:
        _reserve_stock_or_raise(booking)
    except PaymentVerificationError:
        db.session.rollback()
        raise

    payment.razorpay_payment_id = razorpay_payment_id
    payment.razorpay_signature = razorpay_signature
    payment.status = PAYMENT_SUCCESS
    import datetime as dt
    payment.paid_at = dt.datetime.utcnow()
    booking.status = BOOKING_PAID

    try:
        db.session.flush()
    except IntegrityError:
        # e.g. duplicate razorpay_payment_id due to a race / replay — treat as already handled
        db.session.rollback()
        logger.warning("IntegrityError marking payment paid for booking %s", booking.booking_reference)
        existing_payment = Payment.query.filter_by(razorpay_payment_id=razorpay_payment_id).first()
        if existing_payment and existing_payment.booking_id == booking.id:
            return issue_tickets_for_booking(booking)
        raise PaymentVerificationError("Payment already processed elsewhere.")

    tickets = issue_tickets_for_booking(booking)
    db.session.commit()
    return tickets


def handle_webhook_payment_captured(order_id: str, payment_id: str, event_payload: dict):
    """Webhook path: authoritative confirmation from Razorpay itself (signature already
    verified by the caller). Idempotent against duplicate webhook deliveries."""
    payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
    if payment is None:
        logger.warning("Webhook for unknown order_id=%s", order_id)
        return None

    booking = payment.booking

    if payment.status == PAYMENT_SUCCESS:
        # Duplicate webhook delivery — no-op, already processed.
        return issue_tickets_for_booking(booking)

    already_paid_elsewhere = Payment.query.filter(
        Payment.razorpay_payment_id == payment_id, Payment.id != payment.id
    ).first()
    if already_paid_elsewhere:
        logger.warning("Duplicate razorpay_payment_id=%s seen in webhook", payment_id)
        return None

    try:
        _reserve_stock_or_raise(booking)
    except PaymentVerificationError:
        db.session.rollback()
        payment.status = PAYMENT_FAILED
        payment.failure_reason = "Sold out at capture time — refund required"
        booking.status = BOOKING_FAILED
        db.session.commit()
        return None

    payment.razorpay_payment_id = payment_id
    payment.status = PAYMENT_SUCCESS
    import datetime as dt
    payment.paid_at = dt.datetime.utcnow()
    booking.status = BOOKING_PAID

    tickets = issue_tickets_for_booking(booking)
    db.session.commit()
    return tickets


def handle_webhook_payment_failed(order_id: str):
    payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
    if payment is None:
        return
    if payment.status == PAYMENT_SUCCESS:
        return  # never downgrade a confirmed payment
    payment.status = PAYMENT_FAILED
    payment.booking.status = BOOKING_FAILED
    db.session.commit()
