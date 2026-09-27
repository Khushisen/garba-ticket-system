import datetime as dt
from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(20), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    bookings = db.relationship("Booking", back_populates="customer")

    def __repr__(self):
        return f"<Customer {self.name} {self.mobile}>"
