import datetime as dt
from app.extensions import db


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    venue = db.Column(db.String(255), nullable=True)
    dress_code = db.Column(db.String(255), nullable=True)
    contact_info = db.Column(db.String(255), nullable=True)
    rules = db.Column(db.Text, nullable=True)
    poster_url = db.Column(db.String(500), nullable=True)
    # draft = not shown publicly, open = accepting bookings, closed = bookings closed
    status = db.Column(db.String(20), nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    ticket_types = db.relationship(
        "TicketType", back_populates="event", cascade="all, delete-orphan"
    )
    bookings = db.relationship("Booking", back_populates="event")

    @property
    def bookings_open(self):
        return self.status == "open"

    def __repr__(self):
        return f"<Event {self.name} {self.date}>"
