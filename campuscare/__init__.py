"""Application factory."""
import hmac
import os
import secrets
from datetime import timedelta

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from config import Config
from .extensions import db, login_manager


def create_app(config_object=Config):
    app = Flask(__name__, instance_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance"))
    app.config.from_object(config_object)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from .routes import admin, auth, main, staff
    for module in (auth, main, staff, admin):
        app.register_blueprint(module.bp)

    _register_security(app)
    _register_filters(app)
    _register_error_handlers(app)

    with app.app_context():
        from . import models  # noqa: F401  (ensure models are registered)
        db.create_all()
    return app


def _register_security(app):
    @app.before_request
    def csrf_protect():
        if not app.config.get("CSRF_ENABLED") or request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, description="Security token missing or invalid. Reload the page and try again.")

    @app.context_processor
    def inject_helpers():
        def csrf_token():
            if "_csrf" not in session:
                session["_csrf"] = secrets.token_hex(16)
            return session["_csrf"]
        from .constants import BUILDINGS, CATEGORIES, PRIORITIES, ROLE_LABELS, STATUSES
        return dict(csrf_token=csrf_token, BUILDINGS=BUILDINGS, CATEGORIES=CATEGORIES, PRIORITIES=PRIORITIES,
                    STATUSES=STATUSES, ROLE_LABELS=ROLE_LABELS)

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; "
                                                  "style-src 'self' 'unsafe-inline'; script-src 'self'")
        return resp


def _register_filters(app):
    offset = timedelta(hours=app.config["DISPLAY_UTC_OFFSET_HOURS"])

    @app.template_filter("localtime")
    def localtime(dt, fmt="%d %b %Y, %H:%M"):
        return (dt + offset).strftime(fmt) if dt else "—"

    @app.template_filter("slug")
    def slug(value):
        return (value or "").lower().replace(" ", "-")


def _register_error_handlers(app):
    from .services import PermissionDenied, WorkflowError

    @app.errorhandler(PermissionDenied)
    def denied(exc):
        return render_template("errors/error.html", code=403, title="Access denied", message=str(exc)), 403

    @app.errorhandler(WorkflowError)
    def workflow(exc):
        flash(str(exc), "danger")
        ref = (request.view_args or {}).get("ref")
        return redirect(url_for("main.detail", ref=ref) if ref else url_for("main.index"))

    for code, title, msg in [
        (400, "Bad request", "The request could not be processed."),
        (403, "Access denied", "You do not have permission to view this page."),
        (404, "Page not found", "The page or record you requested does not exist."),
        (413, "File too large", "The upload exceeds the maximum allowed size."),
        (500, "Something went wrong", "An unexpected error occurred. The incident has been logged."),
    ]:
        def handler(exc, code=code, title=title, msg=msg):
            desc = getattr(exc, "description", None)
            message = desc if code == 400 and desc else msg
            return render_template("errors/error.html", code=code, title=title, message=message), code
        app.register_error_handler(code, handler)
