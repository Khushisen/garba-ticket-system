import datetime as dt
import click

from app.extensions import db
from app.models import AdminUser, Event, TicketType


def register_commands(app):
    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(username, email, password):
        """Create an admin (full access) staff account."""
        if AdminUser.query.filter_by(username=username).first():
            click.echo("A user with that username already exists.")
            return
        user = AdminUser(username=username, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin user '{username}' created.")

    @app.cli.command("create-scanner")
    @click.option("--username", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--gate-name", prompt=True, default="Gate 1")
    def create_scanner(username, password, gate_name):
        """Create a gate-scanner staff account (limited privileges)."""
        if AdminUser.query.filter_by(username=username).first():
            click.echo("A user with that username already exists.")
            return
        user = AdminUser(username=username, role="scanner", gate_name=gate_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Scanner user '{username}' created for {gate_name}.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Seed a demo Garba event with sample ticket types (for local dev only)."""
        if Event.query.first():
            click.echo("An event already exists; skipping seed.")
            return
        event = Event(
            name="Grand Garba Night 2026",
            description="A festive night of Garba and Dandiya with live dhol, food stalls and prizes for best traditional attire.",
            date=dt.date(2026, 10, 10),
            start_time=dt.time(19, 0),
            end_time=dt.time(23, 30),
            venue="City Convention Grounds, Ajmer",
            dress_code="Traditional Navratri attire encouraged",
            contact_info="+91-90000-00000",
            rules="No outside food or drinks. No smoking/alcohol on premises. Entry closes 30 min before end.",
            status="open",
        )
        db.session.add(event)
        db.session.flush()

        db.session.add_all(
            [
                TicketType(event_id=event.id, name="General Pass", description="Entry + Garba floor access", price=299, total_quantity=500),
                TicketType(event_id=event.id, name="Couple Pass", description="Entry for two", price=499, total_quantity=200),
                TicketType(event_id=event.id, name="VIP Pass", description="Priority entry, reserved seating, welcome drink", price=999, total_quantity=100),
            ]
        )
        db.session.commit()
        click.echo(f"Seeded demo event '{event.name}' with 3 pass types.")
