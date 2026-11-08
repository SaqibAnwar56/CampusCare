"""Business logic. Routes stay thin; every rule that matters (workflow, permissions,
duplicate detection, priority escalation, assignment) lives here so it can be unit tested."""
import csv
import io
import os
import re
import uuid
from datetime import timedelta

from flask import current_app, has_request_context, request
from sqlalchemy import and_, case, func, or_

from .constants import (BUILDINGS, CATEGORIES, CRITICAL_KEYWORDS, EVENT_ASSIGNMENT, EVENT_PRIORITY,
                        EVENT_STATUS, OPEN_STATUSES, PRIORITIES, PRIORITY_RANK, ROLE_ADMIN, ROLE_REQUESTER,
                        ROLE_STAFF, SAFETY_CATEGORY, SLA_HOURS, STATUSES)
from .extensions import db
from .models import (AuditLog, Feedback, MaintenanceRequest, RequestAssignment, RequestUpdate, User, utcnow)


# --------------------------------------------------------------------------- errors
class ServiceError(Exception):
    pass


class ValidationError(ServiceError):
    def __init__(self, errors):
        super().__init__("; ".join(errors.values()))
        self.errors = errors


class PermissionDenied(ServiceError):
    pass


class WorkflowError(ServiceError):
    pass


class DuplicateFound(ServiceError):
    def __init__(self, duplicates):
        super().__init__("Possible duplicate request(s) found")
        self.duplicates = duplicates


# --------------------------------------------------------------------------- audit
def audit(user, action, entity_type=None, entity_id=None, details=""):
    ip = request.remote_addr if has_request_context() else None
    db.session.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type,
                            entity_id=str(entity_id) if entity_id is not None else None,
                            details=details, ip_address=ip))


# --------------------------------------------------------------------------- workflow
# (from_status, to_status) -> roles allowed to perform the transition.
# "Assigned" is reachable only through assign() so an assignee is always recorded.
TRANSITIONS = {
    ("Submitted", "Under Review"): {ROLE_ADMIN},
    ("Submitted", "Rejected"): {ROLE_ADMIN},
    ("Under Review", "Assigned"): {ROLE_ADMIN},
    ("Under Review", "Rejected"): {ROLE_ADMIN},
    ("Assigned", "In Progress"): {ROLE_STAFF},
    ("Assigned", "Under Review"): {ROLE_ADMIN},
    ("In Progress", "Resolved"): {ROLE_STAFF},
    ("In Progress", "Under Review"): {ROLE_ADMIN},
    ("Resolved", "Closed"): {ROLE_REQUESTER, ROLE_ADMIN},
    ("Resolved", "In Progress"): {ROLE_REQUESTER, ROLE_ADMIN},     # re-open: problem not fixed
}
NOTE_REQUIRED = {"Rejected": "A reason is required when rejecting a request.",
                 "Resolved": "Resolution notes (at least 10 characters) are required.",
                 }


def _ownership_ok(req, user, to_status):
    if user.role == ROLE_ADMIN:
        return True
    if user.role == ROLE_REQUESTER:
        return req.requester_id == user.id
    if user.role == ROLE_STAFF:
        a = req.current_assignment
        return bool(a and a.staff_id == user.id)
    return False


def available_actions(req, user):
    """Target statuses the user may select for this request right now."""
    out = []
    for (frm, to), roles in TRANSITIONS.items():
        if frm == req.status and to != "Assigned" and user.role in roles and _ownership_ok(req, user, to):
            out.append(to)
    return out


def transition(req, actor, to_status, note=None):
    if to_status not in STATUSES:
        raise WorkflowError(f"Unknown status '{to_status}'.")
    if to_status == "Assigned":
        raise WorkflowError("A request can only become 'Assigned' by assigning it to a staff member.")
    roles = TRANSITIONS.get((req.status, to_status))
    if roles is None:
        raise WorkflowError(f"Invalid transition: {req.status} → {to_status}.")
    if actor.role not in roles:
        raise PermissionDenied(f"Your role may not change a request from {req.status} to {to_status}.")
    if not _ownership_ok(req, actor, to_status):
        raise PermissionDenied("You are not allowed to act on this request.")
    note = (note or "").strip()
    if to_status == "Rejected" and len(note) < 5:
        raise WorkflowError(NOTE_REQUIRED["Rejected"])
    if to_status == "Resolved" and len(note) < 10:
        raise WorkflowError(NOTE_REQUIRED["Resolved"])
    if req.status == "Resolved" and to_status == "In Progress" and len(note) < 5:
        raise WorkflowError("Please explain why the request is being re-opened.")
    if len(note) > 1000:
        raise WorkflowError("Note is too long (maximum 1000 characters).")

    old = req.status
    req.status = to_status
    now = utcnow()
    if to_status == "Resolved":
        req.resolved_at, req.resolution_notes = now, note
    elif to_status == "Closed":
        req.closed_at = now
    elif old == "Resolved" and to_status == "In Progress":
        req.resolved_at = None
    if to_status == "Under Review":            # pulled back for re-assignment
        for a in req.assignments:
            a.is_active = False
    db.session.add(RequestUpdate(request=req, author_id=actor.id, event_type=EVENT_STATUS,
                                 from_status=old, to_status=to_status, note=note or None))
    audit(actor, "STATUS_CHANGE", "request", req.reference_id, f"{old} -> {to_status}")
    db.session.commit()
    return req


def suggest_staff(category):
    """Active staff ranked by specialty match, then by current workload (fewest open tasks first)."""
    staff = User.query.filter_by(role=ROLE_STAFF, is_active_account=True).all()
    rows = []
    for s in staff:
        load = (db.session.query(func.count(MaintenanceRequest.id))
                .join(RequestAssignment, and_(RequestAssignment.request_id == MaintenanceRequest.id,
                                              RequestAssignment.is_active.is_(True),
                                              RequestAssignment.staff_id == s.id))
                .filter(MaintenanceRequest.status.in_(("Assigned", "In Progress"))).scalar())
        rows.append({"user": s, "open_tasks": load, "match": s.specialty == category})
    rows.sort(key=lambda r: (not r["match"], r["open_tasks"], r["user"].full_name))
    return rows


def assign(req, admin, staff_id, note=None):
    if admin.role != ROLE_ADMIN:
        raise PermissionDenied("Only administrators can assign requests.")
    if req.status not in ("Under Review", "Assigned"):
        raise WorkflowError(f"Requests can be assigned only while 'Under Review' (current status: {req.status}).")
    try:
        staff = db.session.get(User, int(staff_id))
    except (TypeError, ValueError):
        staff = None
    if not staff or staff.role != ROLE_STAFF or not staff.is_active_account:
        raise WorkflowError("Selected user is not an active maintenance staff member.")
    current = req.current_assignment
    if current and current.staff_id == staff.id:
        raise WorkflowError(f"Request is already assigned to {staff.full_name}.")
    old = req.status
    for a in req.assignments:
        a.is_active = False
    db.session.add(RequestAssignment(request=req, staff_id=staff.id, assigned_by_id=admin.id,
                                     note=(note or "").strip()[:255] or None))
    req.status = "Assigned"
    verb = "Reassigned" if current else "Assigned"
    db.session.add(RequestUpdate(request=req, author_id=admin.id, event_type=EVENT_ASSIGNMENT,
                                 from_status=old, to_status="Assigned",
                                 note=f"{verb} to {staff.full_name}" + (f" — {note.strip()}" if note and note.strip() else "")))
    audit(admin, "ASSIGN", "request", req.reference_id, f"{verb} to {staff.email}")
    db.session.commit()
    return req


def change_priority(req, admin, new_priority, reason):
    if admin.role != ROLE_ADMIN:
        raise PermissionDenied("Only administrators can change priority.")
    if new_priority not in PRIORITIES:
        raise WorkflowError("Invalid priority.")
    if not req.is_open:
        raise WorkflowError("Priority can only be changed while the request is open.")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise WorkflowError("Please give a short reason for the priority change.")
    if new_priority == req.priority:
        raise WorkflowError("Request already has that priority.")
    old = req.priority
    req.priority = new_priority
    req.due_at = req.created_at + timedelta(hours=SLA_HOURS[new_priority])
    db.session.add(RequestUpdate(request=req, author_id=admin.id, event_type=EVENT_PRIORITY,
                                 from_status=req.status, to_status=req.status,
                                 note=f"Priority {old} → {new_priority}: {reason}"))
    audit(admin, "PRIORITY_CHANGE", "request", req.reference_id, f"{old} -> {new_priority}")
    db.session.commit()
    return req


# --------------------------------------------------------------------------- request creation
def normalize_location(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def find_duplicates(building, location, category):
    norm = normalize_location(location)
    if len(norm) < 2:
        return []
    candidates = MaintenanceRequest.query.filter(
        MaintenanceRequest.building == building, MaintenanceRequest.category == category,
        MaintenanceRequest.status.in_(OPEN_STATUSES)).all()
    hits = []
    for c in candidates:
        other = normalize_location(c.location)
        if other == norm or (len(norm) >= 3 and norm in other) or (len(other) >= 3 and other in norm):
            hits.append(c)
    return hits


def escalate_priority(category, title, description, requested):
    """Return (effective_priority, reason or None). Safety hazards must not wait in a normal queue."""
    effective, reason = requested, None
    if category == SAFETY_CATEGORY and PRIORITY_RANK[effective] > PRIORITY_RANK["High"]:
        effective, reason = "High", "Safety & Security category has a minimum priority of High."
    text = f"{title} {description}".lower().replace("fire extinguisher", "")
    for kw in CRITICAL_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            if effective != "Critical":
                effective, reason = "Critical", f"Description mentions '{kw}', which indicates immediate danger."
            break
    return effective, reason


def clean_request_form(form):
    data = {
        "title": (form.get("title") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "category": form.get("category") or "",
        "building": form.get("building") or "",
        "location": (form.get("location") or "").strip(),
        "priority": form.get("priority") or "",
    }
    errors = {}
    if not 5 <= len(data["title"]) <= 120:
        errors["title"] = "Title is required (5–120 characters)."
    if not 20 <= len(data["description"]) <= 2000:
        errors["description"] = "Description is required (20–2000 characters) so staff can understand the problem."
    if data["category"] not in CATEGORIES:
        errors["category"] = "Please select a valid category."
    if data["building"] not in BUILDINGS:
        errors["building"] = "Please select a building."
    if not 2 <= len(data["location"]) <= 100:
        errors["location"] = "Specific location (room, floor, corridor) is required."
    if data["priority"] not in PRIORITIES:
        errors["priority"] = "Please select a priority."
    return data, errors


def validate_image(file):
    """Return (bytes, ext) or (None, None). Checks extension, size, and real file signature."""
    if file is None or not getattr(file, "filename", ""):
        return None, None
    name = file.filename
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValidationError({"image": "Only PNG and JPG images are allowed."})
    limit = current_app.config["MAX_IMAGE_BYTES"]
    data = file.read(limit + 1)
    if not data:
        raise ValidationError({"image": "The uploaded image is empty."})
    if len(data) > limit:
        raise ValidationError({"image": f"Image is too large (maximum {limit // (1024 * 1024)} MB)."})
    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpg = data.startswith(b"\xff\xd8\xff")
    if not (is_png or is_jpg) or (ext == "png") != is_png:
        raise ValidationError({"image": "File content does not match an allowed PNG/JPG image."})
    return data, ("png" if is_png else "jpg")


def store_image(data, ext):
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(folder, name), "wb") as fh:
        fh.write(data)
    return name


def create_request(user, form, file=None, confirm_duplicate=False):
    if user.role != ROLE_REQUESTER:
        raise PermissionDenied("Only students and faculty can submit requests.")
    data, errors = clean_request_form(form)
    img_bytes = img_ext = None
    try:
        img_bytes, img_ext = validate_image(file)
    except ValidationError as exc:
        errors.update(exc.errors)
    if errors:
        raise ValidationError(errors)
    duplicates = find_duplicates(data["building"], data["location"], data["category"])
    if duplicates and not confirm_duplicate:
        raise DuplicateFound(duplicates)

    effective, reason = escalate_priority(data["category"], data["title"], data["description"], data["priority"])
    now = utcnow()
    req = MaintenanceRequest(
        reference_id=f"TMP-{uuid.uuid4().hex[:12]}", title=data["title"], description=data["description"],
        category=data["category"], building=data["building"], location=data["location"],
        requested_priority=data["priority"], priority=effective, status="Submitted",
        requester_id=user.id, created_at=now, due_at=now + timedelta(hours=SLA_HOURS[effective]),
        duplicate_of_id=duplicates[0].id if duplicates else None)
    if img_bytes:
        req.image_filename = store_image(img_bytes, img_ext)
    db.session.add(req)
    db.session.flush()
    req.reference_id = f"CC-{now.year}-{req.id:04d}"
    db.session.add(RequestUpdate(request=req, author_id=user.id, event_type=EVENT_STATUS, to_status="Submitted",
                                 note="Request submitted"))
    if reason:
        db.session.add(RequestUpdate(request=req, author_id=user.id, event_type=EVENT_PRIORITY,
                                     from_status="Submitted", to_status="Submitted",
                                     note=f"Priority automatically raised {data['priority']} → {effective}. {reason}"))
    audit(user, "REQUEST_CREATE", "request", req.reference_id,
          f"{req.category} @ {req.building}" + (" [possible duplicate acknowledged]" if duplicates else ""))
    db.session.commit()
    return req


# --------------------------------------------------------------------------- feedback
def submit_feedback(req, user, rating, comment):
    if user.role != ROLE_REQUESTER or req.requester_id != user.id:
        raise PermissionDenied("Only the person who reported the request can leave feedback.")
    if req.status not in ("Resolved", "Closed"):
        raise WorkflowError("Feedback can be given only after the request has been resolved.")
    if req.feedback:
        raise WorkflowError("Feedback has already been submitted for this request.")
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        raise ValidationError({"rating": "Rating must be between 1 and 5."})
    comment = (comment or "").strip()
    if len(comment) > 500:
        raise ValidationError({"comment": "Comment is too long (maximum 500 characters)."})
    db.session.add(Feedback(request=req, user_id=user.id, rating=rating, comment=comment or None))
    audit(user, "FEEDBACK", "request", req.reference_id, f"rating={rating}")
    db.session.commit()


# --------------------------------------------------------------------------- queries
def _priority_order():
    return case(*[(MaintenanceRequest.priority == k, v) for k, v in PRIORITY_RANK.items()], else_=9)


def apply_filters(query, args):
    q = (args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(MaintenanceRequest.title.ilike(like), MaintenanceRequest.reference_id.ilike(like),
                                 MaintenanceRequest.location.ilike(like), MaintenanceRequest.description.ilike(like)))
    for field in ("status", "category", "priority", "building"):
        val = args.get(field)
        if val:
            query = query.filter(getattr(MaintenanceRequest, field) == val)
    if args.get("overdue") == "1":
        query = query.filter(MaintenanceRequest.status.in_(OPEN_STATUSES), MaintenanceRequest.due_at < utcnow())
    sort = args.get("sort", "newest")
    if sort == "priority":
        query = query.order_by(_priority_order(), MaintenanceRequest.due_at)
    elif sort == "due":
        query = query.order_by(MaintenanceRequest.due_at)
    else:
        query = query.order_by(MaintenanceRequest.created_at.desc())
    return query


def requests_for_requester(user):
    return MaintenanceRequest.query.filter_by(requester_id=user.id)


def active_tasks_query(staff):
    return (MaintenanceRequest.query.join(RequestAssignment, and_(
        RequestAssignment.request_id == MaintenanceRequest.id, RequestAssignment.is_active.is_(True),
        RequestAssignment.staff_id == staff.id)))


def can_view(req, user):
    if user.role == ROLE_ADMIN:
        return True
    if user.role == ROLE_REQUESTER:
        return req.requester_id == user.id
    if user.role == ROLE_STAFF:
        return any(a.staff_id == user.id for a in req.assignments)
    return False


# --------------------------------------------------------------------------- statistics & reports
def _count_by(column, rows):
    out = {}
    for r in rows:
        out[getattr(r, column)] = out.get(getattr(r, column), 0) + 1
    return out


def dashboard_stats():
    rows = MaintenanceRequest.query.all()
    now = utcnow()
    resolved = [r for r in rows if r.resolved_at]
    ratings = [r.feedback.rating for r in rows if r.feedback]
    trend = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        trend.append({"label": day.strftime("%d %b"), "count": sum(1 for r in rows if r.created_at.date() == day)})
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r.is_open),
        "overdue": sum(1 for r in rows if r.is_overdue),
        "unassigned": sum(1 for r in rows if r.status in ("Submitted", "Under Review")),
        "resolved": sum(1 for r in rows if r.status in ("Resolved", "Closed")),
        "avg_resolution_hours": round(sum(r.hours_to_resolve for r in resolved) / len(resolved), 1) if resolved else None,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "by_status": {s: sum(1 for r in rows if r.status == s) for s in STATUSES},
        "by_priority": {p: sum(1 for r in rows if r.priority == p and r.is_open) for p in PRIORITIES},
        "by_category": _count_by("category", rows),
        "trend": trend,
    }


def report_summary(date_from=None, date_to=None):
    q = MaintenanceRequest.query
    if date_from:
        q = q.filter(MaintenanceRequest.created_at >= date_from)
    if date_to:
        q = q.filter(MaintenanceRequest.created_at < date_to + timedelta(days=1))
    rows = q.order_by(MaintenanceRequest.created_at).all()
    resolved = [r for r in rows if r.resolved_at]
    on_time = [r for r in resolved if r.resolved_at <= r.due_at]
    by_cat = {}
    for cat in CATEGORIES:
        subset = [r for r in rows if r.category == cat]
        if not subset:
            continue
        res = [r for r in subset if r.resolved_at]
        rated = [r.feedback.rating for r in subset if r.feedback]
        by_cat[cat] = {
            "total": len(subset), "open": sum(1 for r in subset if r.is_open),
            "resolved": len(res), "rejected": sum(1 for r in subset if r.status == "Rejected"),
            "avg_hours": round(sum(r.hours_to_resolve for r in res) / len(res), 1) if res else None,
            "avg_rating": round(sum(rated) / len(rated), 2) if rated else None,
        }
    return {
        "rows": rows, "total": len(rows), "resolved": len(resolved),
        "overdue_open": sum(1 for r in rows if r.is_overdue),
        "sla_compliance": round(100 * len(on_time) / len(resolved), 1) if resolved else None,
        "by_category": by_cat,
        "by_priority": {p: sum(1 for r in rows if r.priority == p) for p in PRIORITIES},
        "by_status": {s: sum(1 for r in rows if r.status == s) for s in STATUSES},
    }


def report_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Reference", "Title", "Category", "Building", "Location", "Priority", "Status", "Assigned To",
                "Created (UTC)", "Due (UTC)", "Resolved (UTC)", "Overdue", "Rating"])
    for r in rows:
        w.writerow([r.reference_id, r.title, r.category, r.building, r.location, r.priority, r.status,
                    r.assigned_staff.full_name if r.assigned_staff else "",
                    r.created_at.strftime("%Y-%m-%d %H:%M"), r.due_at.strftime("%Y-%m-%d %H:%M"),
                    r.resolved_at.strftime("%Y-%m-%d %H:%M") if r.resolved_at else "",
                    "Yes" if r.is_overdue else "No", r.feedback.rating if r.feedback else ""])
    return buf.getvalue()


# --------------------------------------------------------------------------- user management
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_password(pw):
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must be at least 8 characters and contain letters and digits."
    return None


def create_user(full_name, email, password, role, department=None, specialty=None):
    errors = {}
    full_name, email = (full_name or "").strip(), (email or "").strip().lower()
    if not 2 <= len(full_name) <= 100:
        errors["full_name"] = "Full name is required (2–100 characters)."
    if not EMAIL_RE.match(email) or len(email) > 120:
        errors["email"] = "Enter a valid email address."
    elif User.query.filter_by(email=email).first():
        errors["email"] = "An account with this email already exists."
    pw_err = validate_password(password or "")
    if pw_err:
        errors["password"] = pw_err
    if role not in (ROLE_REQUESTER, ROLE_STAFF, ROLE_ADMIN):
        errors["role"] = "Invalid role."
    if errors:
        raise ValidationError(errors)
    user = User(full_name=full_name, email=email, role=role, department=(department or "").strip()[:100] or None,
                specialty=specialty if role == ROLE_STAFF and specialty in CATEGORIES else None)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user
