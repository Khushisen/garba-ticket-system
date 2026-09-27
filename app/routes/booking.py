import re

from flask import Blueprint, request, jsonify, url_for

from app.extensions import limiter
from app.models import Event
from app.services.booking_service import create_booking, BookingError

booking_bp = Blueprint("booking_api", __name__)

MOBILE_RE = re.compile(r"^\+?\d{10,15}$")
NAME_RE = re.compile(r"^[A-Za-z\s.'-]{2,120}$")


def _validate(data):
    errors = {}
    name = (data.get("name") or "").strip()
    mobile = (data.get("mobile") or "").strip()
    email = (data.get("email") or "").strip()
    quantity = data.get("quantity")
    terms = data.get("terms_accepted")

    if not NAME_RE.match(name):
        errors["name"] = "Enter a valid full name."
    if not MOBILE_RE.match(mobile):
        errors["mobile"] = "Enter a valid mobile number."
    if "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Enter a valid email address."
    try:
        q = int(quantity)
        if q < 1 or q > 10:
            raise ValueError()
    except (TypeError, ValueError):
        errors["quantity"] = "Quantity must be between 1 and 10."
    if not terms:
        errors["terms_accepted"] = "You must accept the terms and conditions."

    return errors


@booking_bp.route("", methods=["POST"])
@limiter.limit("20 per minute")
def create_booking_api():
    data = request.get_json(silent=True) or request.form.to_dict()

    errors = _validate(data)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    event_id = data.get("event_id")
    ticket_type_id = data.get("ticket_type_id")
    event = Event.query.get(event_id) if event_id else None
    if event is None:
        return jsonify({"success": False, "errors": {"event_id": "Invalid event."}}), 400

    try:
        booking = create_booking(
            event=event,
            ticket_type_id=ticket_type_id,
            name=data.get("name"),
            mobile=data.get("mobile"),
            email=data.get("email"),
            quantity=data.get("quantity"),
            gender=data.get("gender"),
            age=data.get("age"),
            emergency_contact=data.get("emergency_contact"),
        )
    except BookingError as e:
        return jsonify({"success": False, "errors": {"_general": str(e)}}), 400

    return jsonify(
        {
            "success": True,
            "booking_reference": booking.booking_reference,
            "amount": str(booking.amount),
            "redirect_url": url_for("public.pay_page", reference=booking.booking_reference),
        }
    )
