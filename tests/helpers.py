import hmac
import hashlib
from unittest.mock import patch

import app.services.ticket_delivery as ticket_delivery_module

_orig_build_qr_payload_url = ticket_delivery_module.build_qr_payload_url


def book_and_pay(client, app, event_id, ticket_type_id, name="Rahul Sharma", mobile="9876543210",
                  email="rahul@example.com", quantity=1):
    """Runs a booking through the full API flow (create booking -> create order
    -> verify with a correctly-computed signature) and returns
    (booking_reference, raw_qr_token, response_json)."""
    captured = {}

    def spy(base_url, raw_token):
        captured["raw_token"] = raw_token
        return _orig_build_qr_payload_url(base_url, raw_token)

    resp = client.post(
        "/api/bookings",
        json={
            "event_id": event_id,
            "ticket_type_id": ticket_type_id,
            "name": name,
            "mobile": mobile,
            "email": email,
            "quantity": quantity,
            "terms_accepted": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    booking_reference = resp.get_json()["booking_reference"]

    with patch("app.services.payment_service.razorpay.Client") as MockClient:
        instance = MockClient.return_value
        instance.order.create.return_value = {
            "id": f"order_{booking_reference}",
            "amount": 10000,
            "currency": "INR",
        }
        order_resp = client.post("/api/payment/create-order", json={"booking_reference": booking_reference})
    assert order_resp.status_code == 200, order_resp.get_json()
    order_id = order_resp.get_json()["order_id"]

    key_secret = app.config["RAZORPAY_KEY_SECRET"]
    payment_id = f"pay_{booking_reference}"
    signature = hmac.new(key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()

    with patch.object(ticket_delivery_module, "build_qr_payload_url", spy):
        verify_resp = client.post(
            "/api/payment/verify",
            json={
                "booking_reference": booking_reference,
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            },
        )

    return booking_reference, captured.get("raw_token"), verify_resp
