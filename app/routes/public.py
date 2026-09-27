from flask import Blueprint, render_template, abort

from app.models import Event

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def index():
    event = Event.query.filter(Event.status.in_(["open", "closed"])).order_by(Event.date.asc()).first()
    if event is None:
        return render_template("public/no_event.html")
    ticket_types = [tt for tt in event.ticket_types if tt.status == "active"]
    return render_template("public/index.html", event=event, ticket_types=ticket_types)


@public_bp.route("/book/<int:event_id>/<int:ticket_type_id>")
def book_form(event_id, ticket_type_id):
    event = Event.query.get_or_404(event_id)
    ticket_type = next((tt for tt in event.ticket_types if tt.id == ticket_type_id), None)
    if ticket_type is None:
        abort(404)
    if not ticket_type.is_purchasable:
        abort(400)
    return render_template("public/book_form.html", event=event, ticket_type=ticket_type)


@public_bp.route("/booking/<reference>/pay")
def pay_page(reference):
    from app.models import Booking

    booking = Booking.query.filter_by(booking_reference=reference).first_or_404()
    return render_template(
        "public/pay.html",
        booking=booking,
        event=booking.event,
        razorpay_key_id=_razorpay_key_id(),
    )


def _razorpay_key_id():
    from flask import current_app

    return current_app.config["RAZORPAY_KEY_ID"]
