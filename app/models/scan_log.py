import datetime as dt
from app.extensions import db


class ScanLog(db.Model):
    __tablename__ = "scan_logs"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=True)
    # Kept even when ticket isn't found, for fraud-attempt auditing
    scanned_token_hash = db.Column(db.String(64), nullable=True)

    scanner_user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=True)
    gate_name = db.Column(db.String(80), nullable=True)

    scan_time = db.Column(db.DateTime, default=dt.datetime.utcnow, index=True)
    # VALID | ALREADY_USED | INVALID | CANCELLED | REFUNDED | EXPIRED
    result = db.Column(db.String(20), nullable=False)

    device_information = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)

    ticket = db.relationship("Ticket", back_populates="scan_logs")
    scanner = db.relationship("AdminUser")

    def __repr__(self):
        return f"<ScanLog ticket={self.ticket_id} {self.result}>"
