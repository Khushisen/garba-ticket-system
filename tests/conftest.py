import datetime as dt

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import AdminUser, Event, TicketType


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def seed(app, db):
    admin = AdminUser(username="admin", role="admin")
    admin.set_password("adminpass123")
    scanner = AdminUser(username="scanner1", role="scanner", gate_name="Gate 1")
    scanner.set_password("scannerpass123")
    db.session.add_all([admin, scanner])

    event = Event(name="Test Garba Night", date=dt.date(2026, 10, 10), status="open")
    db.session.add(event)
    db.session.flush()

    ticket_type = TicketType(event_id=event.id, name="General", price=100, total_quantity=3)
    db.session.add(ticket_type)
    db.session.commit()

    return {"event_id": event.id, "ticket_type_id": ticket_type.id}


def get_csrf_token(client, url="/login"):
    import re

    resp = client.get(url)
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.get_data(as_text=True))
    return match.group(1) if match else None


def login(client, username, password):
    token = get_csrf_token(client)
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=True,
    )
