import csv
import datetime as dt
import io

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from sqlalchemy import func, or_

from app.extensions import db, limiter
from app.utils.decorators import admin_required
from app.models import Event, TicketType, Booking, Ticket, Payment, ScanLog, AdminUser
from app.models.booking import BOOKING_PAID
from app.models.payment import PAYMENT_SUCCESS
from app.models.ticket import TICKET_ACTIVE, TICKET_USED, TICKET_CANCELLED, TICKET_REFUNDED

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
@login_required
def dashboard():
    if current_user.is_scanner:
        return redirect(url_for("scanner.scanner_page"))

    total_tickets = Ticket.query.count()
    used_tickets = Ticket.query.filter_by(status=TICKET_USED).count()
    cancelled_tickets = Ticket.query.filter(Ticket.status.in_([TICKET_CANCELLED, TICKET_REFUNDED])).count()
    pending_payments = Booking.query.filter_by(status="PENDING_PAYMENT").count()
    paid_bookings = Booking.query.filter_by(status=BOOKING_PAID).count()

    total_revenue = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.status == PAYMENT_SUCCESS)
        .scalar()
    )

    today = dt.date.today()
    today_entries = ScanLog.query.filter(
        ScanLog.result == "VALID", func.date(ScanLog.scan_time) == today
    ).count()

    recent_scans = ScanLog.query.order_by(ScanLog.scan_time.desc()).limit(15).all()

    ticket_type_breakdown = (
        db.session.query(TicketType.name, func.coalesce(func.sum(TicketType.sold_quantity), 0))
        .group_by(TicketType.name)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        total_tickets=total_tickets,
        used_tickets=used_tickets,
        cancelled_tickets=cancelled_tickets,
        remaining_tickets=max(total_tickets - used_tickets - cancelled_tickets, 0),
        pending_payments=pending_payments,
        paid_bookings=paid_bookings,
        total_revenue=total_revenue,
        today_entries=today_entries,
        recent_scans=recent_scans,
        ticket_type_breakdown=ticket_type_breakdown,
    )


# ---------------------------------------------------------------- Events

@admin_bp.route("/events")
@login_required
@admin_required
def events_list():
    events = Event.query.order_by(Event.date.desc()).all()
    return render_template("admin/events.html", events=events)


@admin_bp.route("/events/new", methods=["GET", "POST"])
@login_required
@admin_required
def event_new():
    if request.method == "POST":
        event = Event(
            name=request.form["name"],
            description=request.form.get("description"),
            date=dt.datetime.strptime(request.form["date"], "%Y-%m-%d").date(),
            start_time=_parse_time(request.form.get("start_time")),
            end_time=_parse_time(request.form.get("end_time")),
            venue=request.form.get("venue"),
            dress_code=request.form.get("dress_code"),
            contact_info=request.form.get("contact_info"),
            rules=request.form.get("rules"),
            status=request.form.get("status", "open"),
        )
        db.session.add(event)
        db.session.commit()
        flash("Event created.", "success")
        return redirect(url_for("admin.events_list"))
    return render_template("admin/event_form.html", event=None)


@admin_bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def event_edit(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == "POST":
        event.name = request.form["name"]
        event.description = request.form.get("description")
        event.date = dt.datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        event.start_time = _parse_time(request.form.get("start_time"))
        event.end_time = _parse_time(request.form.get("end_time"))
        event.venue = request.form.get("venue")
        event.dress_code = request.form.get("dress_code")
        event.contact_info = request.form.get("contact_info")
        event.rules = request.form.get("rules")
        event.status = request.form.get("status", event.status)
        db.session.commit()
        flash("Event updated.", "success")
        return redirect(url_for("admin.events_list"))
    return render_template("admin/event_form.html", event=event)


def _parse_time(value):
    if not value:
        return None
    return dt.datetime.strptime(value, "%H:%M").time()


# ------------------------------------------------------------ Ticket Types

@admin_bp.route("/events/<int:event_id>/ticket-types", methods=["GET", "POST"])
@login_required
@admin_required
def ticket_types(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == "POST":
        tt = TicketType(
            event_id=event.id,
            name=request.form["name"],
            description=request.form.get("description"),
            price=request.form["price"],
            total_quantity=int(request.form["total_quantity"]),
            status="active",
        )
        db.session.add(tt)
        db.session.commit()
        flash("Ticket type added.", "success")
        return redirect(url_for("admin.ticket_types", event_id=event.id))
    return render_template("admin/ticket_types.html", event=event)


@admin_bp.route("/ticket-types/<int:tt_id>/edit", methods=["POST"])
@login_required
@admin_required
def ticket_type_edit(tt_id):
    tt = TicketType.query.get_or_404(tt_id)
    tt.name = request.form.get("name", tt.name)
    tt.description = request.form.get("description", tt.description)
    if request.form.get("price"):
        tt.price = request.form["price"]
    if request.form.get("total_quantity"):
        tt.total_quantity = int(request.form["total_quantity"])
    tt.status = request.form.get("status", tt.status)
    db.session.commit()
    flash("Ticket type updated.", "success")
    return redirect(url_for("admin.ticket_types", event_id=tt.event_id))


@admin_bp.route("/ticket-types/<int:tt_id>/delete", methods=["POST"])
@login_required
@admin_required
def ticket_type_delete(tt_id):
    tt = TicketType.query.get_or_404(tt_id)
    event_id = tt.event_id
    if tt.sold_quantity > 0:
        flash("Cannot delete a ticket type that already has sales — disable it instead.", "error")
    else:
        db.session.delete(tt)
        db.session.commit()
        flash("Ticket type deleted.", "success")
    return redirect(url_for("admin.ticket_types", event_id=event_id))


# ---------------------------------------------------------------- Tickets

@admin_bp.route("/tickets")
@login_required
@admin_required
def tickets_list():
    q = request.args.get("q", "").strip()
    query = Ticket.query.join(Booking)
    if q:
        query = query.filter(
            or_(
                Ticket.ticket_id.ilike(f"%{q}%"),
                Ticket.holder_name.ilike(f"%{q}%"),
                Booking.booking_reference.ilike(f"%{q}%"),
            )
        )
    tickets = query.order_by(Ticket.issued_at.desc()).limit(200).all()
    return render_template("admin/tickets.html", tickets=tickets, q=q)


@admin_bp.route("/tickets/<int:ticket_id>")
@login_required
@admin_required
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template("admin/ticket_detail.html", ticket=ticket)


@admin_bp.route("/tickets/<int:ticket_id>/cancel", methods=["POST"])
@login_required
@admin_required
def ticket_cancel(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    ticket.status = TICKET_CANCELLED
    ticket.cancelled_at = dt.datetime.utcnow()
    db.session.commit()
    flash(f"Ticket {ticket.ticket_id} cancelled.", "success")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket.id))


@admin_bp.route("/tickets/<int:ticket_id>/mark-used", methods=["POST"])
@login_required
@admin_required
def ticket_mark_used(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    ticket.status = TICKET_USED
    ticket.used_at = dt.datetime.utcnow()
    ticket.used_by = f"admin:{current_user.username}"
    db.session.commit()
    flash(f"Ticket {ticket.ticket_id} marked as used.", "success")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket.id))


@admin_bp.route("/tickets/<int:ticket_id>/reset", methods=["POST"])
@login_required
@admin_required
def ticket_reset(ticket_id):
    """Resets a USED ticket back to ACTIVE — for legitimate corrections only
    (e.g. mis-scan). Requires explicit admin confirmation in the UI."""
    ticket = Ticket.query.get_or_404(ticket_id)
    ticket.status = TICKET_ACTIVE
    ticket.used_at = None
    ticket.used_by = None
    db.session.commit()
    flash(f"Ticket {ticket.ticket_id} reset to ACTIVE.", "success")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket.id))


@admin_bp.route("/tickets/export.csv")
@login_required
@admin_required
def tickets_export():
    tickets = Ticket.query.order_by(Ticket.issued_at.desc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["Ticket ID", "Holder Name", "Pass Type", "Status", "Booking Reference", "Issued At", "Used At"]
    )
    for t in tickets:
        writer.writerow(
            [
                t.ticket_id,
                t.holder_name,
                t.ticket_type_name,
                t.status,
                t.booking.booking_reference if t.booking else "",
                t.issued_at.isoformat() if t.issued_at else "",
                t.used_at.isoformat() if t.used_at else "",
            ]
        )
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets_export.csv"},
    )


# ------------------------------------------------------------------ Staff

@admin_bp.route("/staff", methods=["GET", "POST"])
@login_required
@admin_required
def staff():
    if request.method == "POST":
        username = request.form["username"].strip()
        if AdminUser.query.filter_by(username=username).first():
            flash("That username already exists.", "error")
        else:
            user = AdminUser(
                username=username,
                email=request.form.get("email") or None,
                role=request.form.get("role", "scanner"),
                gate_name=request.form.get("gate_name") or None,
            )
            user.set_password(request.form["password"])
            db.session.add(user)
            db.session.commit()
            flash(f"Staff account '{username}' created.", "success")
        return redirect(url_for("admin.staff"))
    staff_users = AdminUser.query.order_by(AdminUser.role, AdminUser.username).all()
    return render_template("admin/staff.html", staff_users=staff_users)


@admin_bp.route("/staff/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def staff_toggle_active(user_id):
    user = AdminUser.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
    else:
        user.is_active_flag = not user.is_active_flag
        db.session.commit()
        flash(f"{user.username} is now {'active' if user.is_active_flag else 'inactive'}.", "success")
    return redirect(url_for("admin.staff"))
