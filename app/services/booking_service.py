import secrets
import string

from app.extensions import db
from app.models import Booking, Customer, TicketType
from app.models.booking import BOOKING_PENDING

ALPHABET = string.ascii_uppercase + string.digits


class BookingError(Exception):
    pass


def _generate_booking_reference():
    for _ in range(20):
        candidate = "BK-" + "".join(secrets.choice(ALPHABET) for _ in range(10))
        if not Booking.query.filter_by(booking_reference=candidate).first():
            return candidate
    raise RuntimeError("Could not generate a unique booking reference")


def create_booking(event, ticket_type_id, name, mobile, email, quantity, gender=None, age=None, emergency_contact=None):
    if not event.bookings_open:
        raise BookingError("Bookings are currently closed for this event.")

    ticket_type = TicketType.query.filter_by(id=ticket_type_id, event_id=event.id).first()
    if ticket_type is None:
        raise BookingError("Invalid pass type selected.")
    if not ticket_type.is_purchasable:
        raise BookingError("This pass type is currently unavailable.")

    quantity = int(quantity)
    if quantity < 1 or quantity > 10:
        raise BookingError("Quantity must be between 1 and 10.")

    # Soft pre-check for UX (hard, authoritative check happens atomically at
    # payment-verification time in payment_service._reserve_stock_or_raise).
    if ticket_type.available_quantity < quantity:
        raise BookingError("Not enough passes remaining for this type.")

    customer = Customer(name=name.strip(), mobile=mobile.strip(), email=email.strip().lower())
    db.session.add(customer)
    db.session.flush()

    amount = ticket_type.price * quantity

    booking = Booking(
        booking_reference=_generate_booking_reference(),
        event_id=event.id,
        customer_id=customer.id,
        ticket_type_id=ticket_type.id,
        quantity=quantity,
        amount=amount,
        status=BOOKING_PENDING,
        gender=gender or None,
        age=int(age) if age else None,
        emergency_contact=emergency_contact or None,
    )
    db.session.add(booking)
    db.session.commit()
    return booking
