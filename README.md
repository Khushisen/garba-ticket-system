# Garba Event Digital Entry Pass & QR Verification System

A production-ready Flask application for selling Garba/Navratri event passes
online, generating a unique cryptographically-secure QR pass for every paid
booking, and verifying entry at the gate with one-time, race-safe QR
scanning.

## Features

- **Public event site** — festive landing page, pass types with live pricing
  and remaining stock, a validated booking form.
- **Razorpay payments** — order creation, mandatory server-side signature
  verification, webhook handling with duplicate-delivery protection. A ticket
  is **only ever issued after independently verified payment** — never from
  the frontend "success" callback alone.
- **Secure QR tickets** — each ticket gets a `secrets`-generated unique token;
  only its SHA-256 hash is stored in the database. Ticket IDs
  (`GARBA26-A7F39K2`) and QR tokens are both globally unique.
- **Digital pass delivery** — a themed PDF (ReportLab) with embedded QR, a
  secure `/ticket/<slug>` web page, and an architecture ready for email/WhatsApp
  delivery.
- **One-time atomic entry scanning** — a mobile camera-based scanner page
  (`/admin/scanner`) that checks tickets in via an atomic
  compare-and-swap database update, so concurrent scans of the same QR from
  different gates can never both succeed.
- **Admin dashboard** — sales/entry stats, event & pass-type management,
  ticket search/cancel/mark-used/reset, CSV export, staff account management
  with **admin** vs **scanner** roles.
- **Security** — password hashing, CSRF protection, rate limiting, input
  validation, SQL-injection-safe ORM queries, no card data ever stored,
  environment-variable secrets, audit scan logs.

## Tech Stack

Flask · SQLAlchemy · PostgreSQL (prod) / SQLite (dev) · Razorpay · `qrcode` +
`secrets` · ReportLab · Flask-Login · Flask-WTF (CSRF) · Flask-Limiter ·
Flask-Mail

## Project Structure

```
garba-ticket-system/
├── app/
│   ├── models/            # Customer, Event, TicketType, Booking, Payment, Ticket, ScanLog, AdminUser
│   ├── routes/             # public, booking, payment, ticket, scanner, admin, auth
│   ├── services/           # payment, ticket, qr, scan, pdf, email, booking, ticket_delivery
│   ├── templates/
│   ├── static/
│   └── utils/decorators.py # admin_required / scanner_or_admin_required
├── tests/                  # auth, payments, tickets, scanner, race-condition, capacity
├── config.py
├── run.py
├── requirements.txt
├── .env.example
└── Dockerfile
```

## 1. Local Setup (Windows / macOS / Linux)

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux
# edit .env: set SECRET_KEY, RAZORPAY_* (test keys are fine locally)
```

By default `DATABASE_URL` is unset, so the app uses local SQLite
(`app/garba.db`) — nothing further to install for local dev.

### Create the database, an admin user, and a demo event

```bash
export FLASK_APP=run.py     # Windows (cmd): set FLASK_APP=run.py

python -c "from app import create_app; from app.extensions import db; app=create_app(); app.app_context().push(); db.create_all()"

flask create-admin          # prompts for username/email/password
flask create-scanner        # prompts for a gate-scanner account
flask seed-demo             # optional: creates a sample event + 3 pass types
```

### Run it

```bash
python run.py
```

Visit `http://127.0.0.1:5000/` for the public site, and
`http://127.0.0.1:5000/login` for staff (admin/scanner) login.

## 2. PostgreSQL (Production Database)

```bash
createdb garba
export DATABASE_URL=postgresql://user:password@localhost:5432/garba
```

The app auto-normalizes `postgres://` URLs (as given by some hosts) to the
`postgresql://` scheme SQLAlchemy expects.

## 3. Razorpay Setup

1. Create a [Razorpay](https://razorpay.com) account, switch to **Test Mode**.
2. Copy your **Key ID** / **Key Secret** from Settings → API Keys into `.env`:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxxxxxx
   ```
3. For webhooks: Settings → Webhooks → Add a webhook pointing to
   `https://your-domain.com/api/payment/webhook`, subscribe to
   `payment.captured` and `payment.failed`, and copy the **Webhook Secret**
   into `RAZORPAY_WEBHOOK_SECRET`.
4. When you go live, switch to live keys — nothing else in the code changes.

### Testing payments locally without a public URL

Razorpay Checkout works fine against `http://127.0.0.1:5000` in test mode for
the `create-order`/`verify` flow. Webhooks need a public HTTPS URL — use a
tunnel (e.g. `ngrok http 5000`) during development if you want to test the
webhook path end-to-end.

## 4. Creating an Event & Pass Types

Log in as an **admin** → **Events** → **New Event** → fill in date/venue/etc.
→ **Save**. Then open the event's **Pass Types** page to add General/Couple/
VIP passes with price and total quantity. Nothing is hard-coded — add, edit,
disable, or delete pass types any time (deleting is blocked once a type has
sales; disable it instead).

## 5. Using the Scanner

Log in with a **scanner** account (created via `flask create-scanner`, or by
an admin under **Staff**) → you're taken straight to `/admin/scanner`. Grant
camera permission; point at a guest's QR. Results are large, color-coded, and
vibrate on the device where supported. Multiple gates can run simultaneously —
they all hit the same central database, so a ticket used at Gate 1
immediately shows **ALREADY USED** at Gate 2.

## 6. Running Tests

```bash
pip install pytest
pytest tests/ -v
```

Included test coverage:
- **Auth** — admin/scanner login, wrong password, unauthorized/role-restricted access
- **Payments** — full pay→ticket flow, tampered-signature rejection, idempotent
  duplicate verify/webhook calls, webhook signature verification
- **Tickets** — ticket ID / QR token / secure-slug uniqueness, unpredictability,
  cancelled/refunded tickets denied at the gate
- **Scanner** — first scan succeeds, second scan on the same QR fails, invalid
  QR rejected, scan audit logging, scanners blocked from admin-only actions
- **Race condition** — two (and eight) simultaneous scans of the *same* ticket
  using real threads against a file-backed database: exactly one ever wins
- **Capacity** — booking-time quantity limits, and concurrent payment
  confirmations for the *last remaining pass* never oversell

## 7. Deployment (Render / Railway / PythonAnywhere / VPS)

### Render / Railway
1. Push this repo to GitHub.
2. Create a new Web Service, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn run:app`
5. Add a managed PostgreSQL instance; set `DATABASE_URL` to its connection
   string.
6. Set all other `.env.example` variables in the platform's environment
   variable settings (never commit `.env`).
7. After first deploy, open a one-off shell/console and run:
   ```bash
   python -c "from app import create_app; from app.extensions import db; app=create_app('production'); app.app_context().push(); db.create_all()"
   flask create-admin
   ```
8. Point your Razorpay webhook at `https://<your-app>.onrender.com/api/payment/webhook`.

### PythonAnywhere
Upload the project, create a virtualenv, `pip install -r requirements.txt`,
configure a WSGI file that imports `app` from `run.py`, and set environment
variables under the Web tab's "Environment variables" section (or load them
from a `.env` file with `python-dotenv`, already wired into `run.py`).

### Generic VPS
```bash
pip install -r requirements.txt
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```
Put Nginx in front for TLS termination and static file serving, and use
`certbot` for HTTPS. Set `APP_ENV=production` so `SESSION_COOKIE_SECURE=True`
takes effect (requires HTTPS to work correctly).

### Domain & HTTPS
Point your domain's DNS to the host, set `BASE_URL` in `.env` to
`https://your-domain.com` (this is embedded in every QR code and ticket
link), and terminate TLS at your platform/load balancer or via
Nginx+certbot on a VPS.

## Security Notes

- Card numbers, UPI PINs, and CVVs are **never** collected or stored — only
  Razorpay's own order/payment identifiers and status.
- QR tokens are stored **hashed** (SHA-256); the raw token exists only in the
  PDF/QR image generated at issuance time and is not recoverable from the
  database.
- All admin/scanner actions require login; role checks (`admin_required`,
  `scanner_or_admin_required`) gate every sensitive route — scanners cannot
  cancel tickets, edit prices, or export financial data.
- CSRF protection is enabled globally; the Razorpay webhook and the
  fetch()-based JSON APIs (booking, scanner) are explicitly exempted since
  they're authenticated by signature or session+role instead.
- Ticket check-in uses a single atomic `UPDATE ... WHERE status = 'ACTIVE'`
  statement rather than a check-then-write pattern, so it is safe under
  concurrent access on SQLite, PostgreSQL, and MySQL alike (see
  `app/services/scan_service.py`).

## Troubleshooting

- **"Not enough tickets remaining" errors on legitimate bookings** — someone
  else bought the last pass between the booking form and payment; this is the
  overselling protection working as intended. Refund/cancel and let the
  customer retry.
- **Webhook returns 400** — check `RAZORPAY_WEBHOOK_SECRET` matches exactly
  what's configured in the Razorpay dashboard for that webhook endpoint.
- **QR won't scan** — ensure the scanner device has camera permission and is
  served over HTTPS (or `127.0.0.1` for local testing) — browsers block
  camera access on plain HTTP for non-localhost origins.
- **PDF/QR missing on the ticket page right after payment** — generation
  happens synchronously in the verify/webhook call; refresh after a few
  seconds if it was somehow delayed.
