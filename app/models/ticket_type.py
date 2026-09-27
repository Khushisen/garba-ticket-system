import datetime as dt
from app.extensions import db


class TicketType(db.Model):
    __tablename__ = "ticket_types"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    total_quantity = db.Column(db.Integer, nullable=False, default=0)
    sold_quantity = db.Column(db.Integer, nullable=False, default=0)
    # active | disabled
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    event = db.relationship("Event", back_populates="ticket_types")
    bookings = db.relationship("Booking", back_populates="ticket_type")

    @property
    def available_quantity(self):
        return max(self.total_quantity - self.sold_quantity, 0)

    @property
    def is_purchasable(self):
        return self.status == "active" and self.available_quantity > 0

    def __repr__(self):
        return f"<TicketType {self.name} ₹{self.price}>"
