import datetime as dt

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter
from app.models import AdminUser

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = AdminUser.query.filter_by(username=username).first()

        if user and user.is_active and user.check_password(password):
            login_user(user)
            user.last_login_at = dt.datetime.utcnow()
            db.session.commit()
            next_url = request.args.get("next")
            if user.is_scanner and not next_url:
                return redirect(url_for("scanner.scanner_page"))
            return redirect(next_url or url_for("admin.dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
