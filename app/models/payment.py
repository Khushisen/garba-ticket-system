import datetime as dt
from app.extensions import db

PAYMENT_PENDING = "PAYMENT_PENDING"
PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
PAYMENT_FAILED = "PAYMENT_FAILED"
PAYMENT_REFUNDED = "REFUNDED"
PAYMENT_CANCELLED = "CANCELLED"


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False, unique=True)

    razorpay_order_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    razorpay_payment_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    razorpay_signature = db.Column(db.String(255), nullable=True)

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=PAYMENT_PENDING, index=True)
    payment_method = db.Column(db.String(40), nullable=True)

    # Never store card numbers, CVVs, UPI PINs etc. Only identifiers/metadata above.
    failure_reason = db.Column(db.String(255), nullable=True)

    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    booking = db.relationship("Booking", back_populates="payment")

    def __repr__(self):
        return f"<Payment booking={self.booking_id} {self.status}>"
