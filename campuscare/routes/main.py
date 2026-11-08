"""Routes shared by all roles plus the Student/Faculty interface."""
import os

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from flask_login import current_user, login_required

from ..constants import ROLE_ADMIN, ROLE_REQUESTER, ROLE_STAFF
from ..models import MaintenanceRequest
from ..services import (DuplicateFound, PermissionDenied, ValidationError, available_actions, can_view,
                        create_request, find_duplicates, apply_filters, requests_for_requester,
                        submit_feedback, suggest_staff, transition)
from . import role_required

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    target = {ROLE_ADMIN: "admin.dashboard", ROLE_STAFF: "staff.dashboard"}.get(current_user.role, "main.dashboard")
    return redirect(url_for(target))


@bp.route("/dashboard")
@role_required(ROLE_REQUESTER)
def dashboard():
    mine = requests_for_requester(current_user).order_by(MaintenanceRequest.created_at.desc()).all()
    stats = {
        "total": len(mine),
        "open": sum(1 for r in mine if r.is_open),
        "in_progress": sum(1 for r in mine if r.status in ("Assigned", "In Progress")),
        "awaiting": [r for r in mine if r.status == "Resolved"],
    }
    return render_template("requests/dashboard.html", stats=stats, recent=mine[:6])


@bp.route("/requests")
@role_required(ROLE_REQUESTER)
def my_requests():
    page = request.args.get("page", 1, type=int)
    pagination = apply_filters(requests_for_requester(current_user), request.args).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("requests/list.html", pagination=pagination, scope="mine", title="My Requests")


@bp.route("/requests/new", methods=["GET", "POST"])
@role_required(ROLE_REQUESTER)
def new_request():
    form, errors, duplicates = {}, {}, []
    if request.method == "POST":
        form = request.form
        try:
            req = create_request(current_user, request.form, request.files.get("image"),
                                 confirm_duplicate=request.form.get("confirm_duplicate") == "1")
            flash(f"Request {req.reference_id} submitted successfully.", "success")
            return redirect(url_for("main.detail", ref=req.reference_id))
        except ValidationError as exc:
            errors = exc.errors
            return render_template("requests/form.html", form=form, errors=errors, duplicates=[]), 422
        except DuplicateFound as exc:
            duplicates = exc.duplicates
            return render_template("requests/form.html", form=form, errors={}, duplicates=duplicates), 409
    return render_template("requests/form.html", form=form, errors=errors, duplicates=duplicates)


@bp.route("/api/duplicates")
@role_required(ROLE_REQUESTER)
def api_duplicates():
    hits = find_duplicates(request.args.get("building", ""), request.args.get("location", ""),
                           request.args.get("category", ""))
    return jsonify([{"reference_id": r.reference_id, "title": r.title, "status": r.status,
                     "url": url_for("main.detail", ref=r.reference_id)} for r in hits])


@bp.route("/requests/<ref>")
@login_required
def detail(ref):
    req = MaintenanceRequest.query.filter_by(reference_id=ref).first_or_404()
    if not can_view(req, current_user):
        raise PermissionDenied("You do not have access to this request.")
    ctx = dict(req=req, actions=available_actions(req, current_user))
    if current_user.role == ROLE_ADMIN:
        ctx["staff_options"] = suggest_staff(req.category)
    ctx["can_feedback"] = (current_user.role == ROLE_REQUESTER and req.requester_id == current_user.id
                           and req.status in ("Resolved", "Closed") and req.feedback is None)
    return render_template("requests/detail.html", **ctx)


@bp.route("/requests/<ref>/transition", methods=["POST"])
@login_required
def do_transition(ref):
    req = MaintenanceRequest.query.filter_by(reference_id=ref).first_or_404()
    if not can_view(req, current_user):
        raise PermissionDenied("You do not have access to this request.")
    transition(req, current_user, request.form.get("to_status", ""), request.form.get("note"))
    flash(f"Status updated to {req.status}.", "success")
    return redirect(url_for("main.detail", ref=ref))


@bp.route("/requests/<ref>/feedback", methods=["POST"])
@role_required(ROLE_REQUESTER)
def feedback(ref):
    req = MaintenanceRequest.query.filter_by(reference_id=ref).first_or_404()
    if not can_view(req, current_user):
        raise PermissionDenied("You do not have access to this request.")
    try:
        submit_feedback(req, current_user, request.form.get("rating"), request.form.get("comment"))
        flash("Thank you — your feedback has been recorded.", "success")
    except ValidationError as exc:
        flash(" ".join(exc.errors.values()), "danger")
    return redirect(url_for("main.detail", ref=ref))


@bp.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    """Images are served only to people who may view the owning request (not as public static files)."""
    req = MaintenanceRequest.query.filter_by(image_filename=filename).first_or_404()
    if not can_view(req, current_user):
        abort(403)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
