from datetime import timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..constants import ROLE_REQUESTER
from ..extensions import db
from ..models import User, utcnow
from ..services import ValidationError, audit, create_user

bp = Blueprint("auth", __name__)


def _safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        ok = False
        if user and user.is_active_account and not user.is_locked() and user.check_password(password):
            ok = True
        if ok:
            user.failed_attempts, user.locked_until = 0, None
            audit(user, "LOGIN", "user", user.id)
            db.session.commit()
            login_user(user)
            return redirect(_safe_next(request.args.get("next")) or url_for("main.index"))
        if user and not user.is_locked():
            user.failed_attempts += 1
            if user.failed_attempts >= current_app.config["MAX_FAILED_LOGINS"]:
                user.locked_until = utcnow() + timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
                user.failed_attempts = 0
                audit(user, "ACCOUNT_LOCKED", "user", user.id, "Too many failed login attempts")
        audit(user, "LOGIN_FAILED", "user", user.id if user else None, f"email={email[:80]}")
        db.session.commit()
        # One generic message: does not reveal whether the account exists or is locked.
        flash("Invalid email or password, or the account is temporarily unavailable.", "danger")
        return render_template("auth/login.html", email=email), 401
    return render_template("auth/login.html", email="")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = {"full_name": "", "email": "", "department": ""}
    errors = {}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        if request.form.get("password") != request.form.get("confirm_password"):
            errors["confirm_password"] = "Passwords do not match."
        try:
            # Self-registration ALWAYS creates a Student/Faculty account; any posted role is ignored.
            user = create_user(form["full_name"], form["email"], request.form.get("password"),
                               ROLE_REQUESTER, form["department"])
            if errors:
                db.session.rollback()
                raise ValidationError(errors)
            audit(user, "REGISTER", "user", user.id)
            db.session.commit()
            flash("Account created. You can now sign in.", "success")
            return redirect(url_for("auth.login"))
        except ValidationError as exc:
            errors.update(exc.errors)
            db.session.rollback()
            return render_template("auth/register.html", form=form, errors=errors), 422
    return render_template("auth/register.html", form=form, errors=errors)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit(current_user, "LOGOUT", "user", current_user.id)
    db.session.commit()
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
