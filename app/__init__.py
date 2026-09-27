import os

from flask import Flask

from config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter, mail


def create_app(config_name=None, config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)

    config_name = config_name or os.environ.get("APP_ENV", "development")
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    # NOTE: Flask-SQLAlchemy builds its engine(s) eagerly inside db.init_app()
    # below, reading config at that exact moment — changes to app.config made
    # AFTER create_app() returns (e.g. mutating app.config post-hoc in a test)
    # have no effect on which database engine gets used. Any test or caller
    # that needs a different DATABASE_URI/engine options must pass them here.
    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["TICKET_PDF_DIR"], exist_ok=True)
    os.makedirs(app.config["TICKET_QR_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)

    from app.models import AdminUser

    @login_manager.user_loader
    def load_user(user_id):
        return AdminUser.query.get(int(user_id))

    from app.routes.public import public_bp
    from app.routes.booking import booking_bp
    from app.routes.payment import payment_bp
    from app.routes.ticket import ticket_bp
    from app.routes.scanner import scanner_bp
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(booking_bp, url_prefix="/api/bookings")
    app.register_blueprint(payment_bp, url_prefix="/api/payment")
    app.register_blueprint(ticket_bp)
    app.register_blueprint(scanner_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(auth_bp)

    # Razorpay webhook must accept raw body -> exempt from CSRF (it is verified
    # by HMAC signature instead, which is a stronger guarantee for this endpoint).
    csrf.exempt(payment_bp)
    # These are pure JSON APIs called via fetch(), authenticated by session +
    # (for the booking API) rate limiting; scanner API is additionally gated
    # by login_required + role check, which is the meaningful protection here.
    csrf.exempt(booking_bp)
    csrf.exempt(scanner_bp)

    from app.commands import register_commands
    register_commands(app)

    @app.context_processor
    def inject_globals():
        return {"app_env": app.config.get("APP_ENV")}

    return app
