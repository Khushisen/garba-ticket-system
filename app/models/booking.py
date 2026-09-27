import datetime as dt
from app.extensions import db

# Booking lifecycle states
BOOKING_PENDING = "PENDING_PAYMENT"
BOOKING_PAID = "PAID"
BOOKING_FAILED = "FAILED"
BOOKING_CANCELLED = "CANCELLED"
BOOKING_REFUNDED = "REFUNDED"


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    booking_reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    ticket_type_id = db.Column(db.Integer, db.ForeignKey("ticket_types.id"), nullable=False)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    amount = db.Column(db.Numeric(10, 2), nullable=False)  # total amount in INR
    status = db.Column(db.String(20), nullable=False, default=BOOKING_PENDING, index=True)

    gender = db.Column(db.String(20), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    emergency_contact = db.Column(db.String(30), nullable=True)

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    event = db.relationship("Event", back_populates="bookings")
    customer = db.relationship("Customer", back_populates="bookings")
    ticket_type = db.relationship("TicketType", back_populates="bookings")
    payment = db.relationship("Payment", back_populates="booking", uselist=False)
    tickets = db.relationship("Ticket", back_populates="booking", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Booking {self.booking_reference} {self.status}>"
