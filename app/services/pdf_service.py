import io

from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.services.qr_service import generate_qr_png_bytes, build_qr_payload_url

MAROON = HexColor("#6b1d3f")
GOLD = HexColor("#d4a72c")
CREAM = HexColor("#fdf6e9")


def build_ticket_pdf(ticket, booking, event, raw_token, base_url) -> bytes:
    """Generates a Garba-themed A6 ticket PDF with an embedded QR code.
    Returns raw PDF bytes (does not touch the filesystem, caller decides where to store it)."""
    buf = io.BytesIO()
    width, height = A6
    c = canvas.Canvas(buf, pagesize=A6)

    # Background
    c.setFillColor(CREAM)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # Header band
    c.setFillColor(MAROON)
    c.rect(0, height - 28 * mm, width, 28 * mm, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(width / 2, height - 12 * mm, event.name.upper() if event else "GARBA NIGHT")
    c.setFont("Helvetica", 9)
    date_str = event.date.strftime("%d %B %Y") if event and event.date else ""
    time_str = event.start_time.strftime("%I:%M %p") if event and event.start_time else ""
    c.drawCentredString(width / 2, height - 19 * mm, f"{date_str}  |  {time_str} onwards")
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width / 2, height - 25 * mm, event.venue or "" if event else "")

    y = height - 36 * mm
    c.setFillColor(MAROON)

    def field(label, value):
        nonlocal y
        c.setFont("Helvetica", 7)
        c.setFillColor(HexColor("#888888"))
        c.drawString(8 * mm, y, label.upper())
        y -= 4.2 * mm
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(MAROON)
        c.drawString(8 * mm, y, str(value))
        y -= 7 * mm

    field("Name", ticket.holder_name)
    field("Pass Type", ticket.ticket_type_name)
    field("Ticket ID", ticket.ticket_id)

    # QR code
    qr_url = build_qr_payload_url(base_url, raw_token)
    qr_bytes = generate_qr_png_bytes(qr_url)
    qr_img = ImageReader(io.BytesIO(qr_bytes))
    qr_size = 34 * mm
    c.drawImage(
        qr_img,
        (width - qr_size) / 2,
        y - qr_size,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )
    y -= qr_size + 5 * mm

    c.setFillColor(GOLD)
    c.roundRect(6 * mm, y - 6 * mm, width - 12 * mm, 6 * mm, 2, fill=1, stroke=0)
    c.setFillColor(MAROON)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(width / 2, y - 4.2 * mm, "PAYMENT STATUS: PAID")
    y -= 10 * mm

    c.setFont("Helvetica", 6.5)
    c.setFillColor(HexColor("#666666"))
    c.drawCentredString(width / 2, y, "This ticket is valid for ONE entry only. Non-transferable once scanned.")
    y -= 3.5 * mm
    if event and event.contact_info:
        c.drawCentredString(width / 2, y, f"Contact: {event.contact_info}")

    c.showPage()
    c.save()
    return buf.getvalue()
