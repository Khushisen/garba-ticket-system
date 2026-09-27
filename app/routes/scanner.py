import re

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.extensions import limiter
from app.utils.decorators import scanner_or_admin_required
from app.services.scan_service import verify_and_checkin

scanner_bp = Blueprint("scanner", __name__)

TOKEN_RE = re.compile(r"/verify/([A-Za-z0-9_\-]+)")


def _extract_token(raw_value: str) -> str:
    """Accepts either a bare token or a full scanned QR URL and returns just the token."""
    if not raw_value:
        return ""
    match = TOKEN_RE.search(raw_value)
    if match:
        return match.group(1)
    return raw_value.strip()


@scanner_bp.route("/admin/scanner")
@login_required
@scanner_or_admin_required
def scanner_page():
    return render_template("scanner/scan.html", gate_name=current_user.gate_name)


@scanner_bp.route("/api/scanner/verify", methods=["POST"])
@login_required
@scanner_or_admin_required
@limiter.limit("120 per minute")
def api_verify():
    data = request.get_json(silent=True) or {}
    raw_token = _extract_token(data.get("qr_data", ""))
    gate_name = data.get("gate_name") or current_user.gate_name
    device_info = request.headers.get("User-Agent", "")[:255]
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)

    result, ticket, message = verify_and_checkin(
        raw_token,
        scanner_user=current_user,
        gate_name=gate_name,
        device_info=device_info,
        ip_address=ip_address,
    )

    payload = {"result": result, "message": message}
    if ticket is not None:
        payload["ticket"] = {
            "ticket_id": ticket.ticket_id,
            "holder_name": ticket.holder_name,
            "ticket_type_name": ticket.ticket_type_name,
            "used_at": ticket.used_at.strftime("%I:%M %p") if ticket.used_at else None,
            "mobile_last4": ticket.mobile_last4,
        }
    return jsonify(payload)


# Also exposed under the documented /api/scanner/check-in path (identical behavior)
scanner_bp.add_url_rule(
    "/api/scanner/check-in", view_func=api_verify, methods=["POST"], endpoint="api_checkin"
)
