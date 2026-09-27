import datetime as dt
from app.extensions import db

TICKET_ACTIVE = "ACTIVE"
TICKET_USED = "USED"
TICKET_CANCELLED = "CANCELLED"
TICKET_REFUNDED = "REFUNDED"
TICKET_EXPIRED = "EXPIRED"


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False)

    ticket_id = db.Column(db.String(40), unique=True, nullable=False, index=True)  # e.g. GARBA26-A7F39K2
    # SHA-256 hash of the raw secret token. Raw token is only ever embedded in the QR/PDF.
    qr_token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # Short public-facing secure identifier used in /ticket/<secure_ticket_slug> URLs.
    secure_slug = db.Column(db.String(64), unique=True, nullable=False, index=True)

    holder_name = db.Column(db.String(120), nullable=False)
    ticket_type_name = db.Column(db.String(120), nullable=False)  # snapshot at issue time
    mobile_last4 = db.Column(db.String(4), nullable=True)

    status = db.Column(db.String(20), nullable=False, default=TICKET_ACTIVE, index=True)

    issued_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    used_at = db.Column(db.DateTime, nullable=True)
    used_by = db.Column(db.String(80), nullable=True)  # scanner username / gate name
    cancelled_at = db.Column(db.DateTime, nullable=True)

    booking = db.relationship("Booking", back_populates="tickets")
    scan_logs = db.relationship("ScanLog", back_populates="ticket", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Ticket {self.ticket_id} {self.status}>"
