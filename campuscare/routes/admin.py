from datetime import datetime

from flask import (Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, url_for)
from flask_login import current_user

from ..constants import ROLES, ROLE_ADMIN, ROLE_STAFF
from ..extensions import db
from ..models import AuditLog, MaintenanceRequest, User
from ..services import (ValidationError, apply_filters, assign, audit, change_priority, create_user,
                        dashboard_stats, report_csv, report_summary)
from . import role_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/dashboard")
@role_required(ROLE_ADMIN)
def dashboard():
    stats = dashboard_stats()
    attention = (MaintenanceRequest.query.filter(MaintenanceRequest.status.in_(("Submitted", "Under Review")))
                 .all())
    attention.sort(key=lambda r: (["Critical", "High", "Medium", "Low"].index(r.priority), r.due_at))
    overdue = [r for r in MaintenanceRequest.query.all() if r.is_overdue]
    overdue.sort(key=lambda r: r.due_at)
    recent = AuditLog.query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(6).all()
    return render_template("admin/dashboard.html", stats=stats, attention=attention[:6], overdue=overdue[:6],
                           recent=recent)


@bp.route("/api/stats")
@role_required(ROLE_ADMIN)
def api_stats():
    return jsonify(dashboard_stats())


@bp.route("/requests")
@role_required(ROLE_ADMIN)
def requests_list():
    page = request.args.get("page", 1, type=int)
    pagination = apply_filters(MaintenanceRequest.query, request.args).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("requests/list.html", pagination=pagination, scope="admin", title="All Requests")


@bp.route("/requests/<ref>/assign", methods=["POST"])
@role_required(ROLE_ADMIN)
def assign_request(ref):
    req = MaintenanceRequest.query.filter_by(reference_id=ref).first_or_404()
    assign(req, current_user, request.form.get("staff_id"), request.form.get("note"))
    flash(f"{ref} assigned to {req.assigned_staff.full_name}.", "success")
    return redirect(url_for("main.detail", ref=ref))


@bp.route("/requests/<ref>/priority", methods=["POST"])
@role_required(ROLE_ADMIN)
def priority(ref):
    req = MaintenanceRequest.query.filter_by(reference_id=ref).first_or_404()
    change_priority(req, current_user, request.form.get("priority"), request.form.get("reason"))
    flash(f"Priority changed to {req.priority}.", "success")
    return redirect(url_for("main.detail", ref=ref))


# ------------------------------------------------------------------ users
@bp.route("/users")
@role_required(ROLE_ADMIN)
def users():
    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        query = query.filter(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    if request.args.get("role") in ROLES:
        query = query.filter_by(role=request.args["role"])
    return render_template("admin/users.html", users=query.order_by(User.role, User.full_name).all())


@bp.route("/users/new", methods=["GET", "POST"])
@role_required(ROLE_ADMIN)
def new_user():
    form, errors = {}, {}
    if request.method == "POST":
        form = request.form
        try:
            user = create_user(form.get("full_name"), form.get("email"), form.get("password"), form.get("role"),
                               form.get("department"), form.get("specialty"))
            audit(current_user, "USER_CREATE", "user", user.id, f"role={user.role}")
            db.session.commit()
            flash(f"User {user.email} created.", "success")
            return redirect(url_for("admin.users"))
        except ValidationError as exc:
            db.session.rollback()
            return render_template("admin/user_form.html", form=form, errors=exc.errors), 422
    return render_template("admin/user_form.html", form=form, errors=errors)


@bp.route("/users/<int:user_id>/update", methods=["POST"])
@role_required(ROLE_ADMIN)
def update_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot change your own role or deactivate your own account.", "danger")
        return redirect(url_for("admin.users"))
    role = request.form.get("role")
    if role in ROLES and role != user.role:
        audit(current_user, "ROLE_CHANGE", "user", user.id, f"{user.role} -> {role}")
        user.role = role
        if role != ROLE_STAFF:
            user.specialty = None
    if request.form.get("toggle_active"):
        user.is_active_account = not user.is_active_account
        audit(current_user, "USER_ACTIVATE" if user.is_active_account else "USER_DEACTIVATE", "user", user.id)
    db.session.commit()
    flash(f"User {user.email} updated.", "success")
    return redirect(url_for("admin.users"))


# ------------------------------------------------------------------ reports & audit
def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


@bp.route("/reports")
@role_required(ROLE_ADMIN)
def reports():
    d_from, d_to = _parse_date(request.args.get("from")), _parse_date(request.args.get("to"))
    summary = report_summary(d_from, d_to)
    return render_template("admin/reports.html", s=summary, d_from=request.args.get("from", ""),
                           d_to=request.args.get("to", ""))


@bp.route("/reports.csv")
@role_required(ROLE_ADMIN)
def reports_csv():
    summary = report_summary(_parse_date(request.args.get("from")), _parse_date(request.args.get("to")))
    audit(current_user, "REPORT_EXPORT", "report", None, f"{summary['total']} rows")
    db.session.commit()
    return Response(report_csv(summary["rows"]), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=campuscare_report.csv"})


@bp.route("/audit")
@role_required(ROLE_ADMIN)
def audit_log():
    page = request.args.get("page", 1, type=int)
    q = AuditLog.query
    if request.args.get("action"):
        q = q.filter_by(action=request.args["action"])
    pagination = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).paginate(page=page, per_page=20,
                                                                                    error_out=False)
    actions = [a for (a,) in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    return render_template("admin/audit.html", pagination=pagination, actions=actions)
