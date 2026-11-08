from flask import Blueprint, current_app, render_template, request

from ..constants import ROLE_STAFF
from ..models import MaintenanceRequest, utcnow
from ..services import active_tasks_query, apply_filters
from . import role_required
from flask_login import current_user

bp = Blueprint("staff", __name__, url_prefix="/staff")


@bp.route("/dashboard")
@role_required(ROLE_STAFF)
def dashboard():
    tasks = apply_filters(active_tasks_query(current_user).filter(
        MaintenanceRequest.status.in_(("Assigned", "In Progress"))), {"sort": "priority"}).all()
    done = active_tasks_query(current_user).filter(MaintenanceRequest.status.in_(("Resolved", "Closed"))).all()
    stats = {
        "pending": sum(1 for t in tasks if t.status == "Assigned"),
        "in_progress": sum(1 for t in tasks if t.status == "In Progress"),
        "overdue": sum(1 for t in tasks if t.is_overdue),
        "completed": len(done),
    }
    return render_template("staff/dashboard.html", tasks=tasks, stats=stats)


@bp.route("/history")
@role_required(ROLE_STAFF)
def history():
    page = request.args.get("page", 1, type=int)
    q = active_tasks_query(current_user).filter(MaintenanceRequest.status.in_(("Resolved", "Closed")))
    pagination = q.order_by(MaintenanceRequest.resolved_at.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("staff/history.html", pagination=pagination)
