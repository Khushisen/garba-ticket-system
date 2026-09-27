import datetime as dt
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class AdminUser(UserMixin, db.Model):
    """Staff accounts. role is 'admin' (full access) or 'scanner' (gate staff)."""

    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="scanner")  # admin | scanner
    gate_name = db.Column(db.String(80), nullable=True)  # e.g. "Gate 1", "VIP Gate"
    is_active_flag = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_active(self):
        # Overrides UserMixin.is_active property
        return self.is_active_flag

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_scanner(self):
        return self.role == "scanner"

    def __repr__(self):
        return f"<AdminUser {self.username} ({self.role})>"
