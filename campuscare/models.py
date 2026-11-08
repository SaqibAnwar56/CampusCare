"""SQLAlchemy models. The schema is documented in docs/DATABASE.md and the ER diagram."""
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index
from werkzeug.security import check_password_hash, generate_password_hash

from .constants import OPEN_STATUSES, PRIORITIES, ROLES, STATUSES
from .extensions import db, login_manager


def utcnow():
    """Naive UTC timestamp (stored uniformly in UTC, converted only for display)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('requester','staff','admin')", name="ck_users_role"),)

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    department = db.Column(db.String(100))
    specialty = db.Column(db.String(50))               # staff only: preferred category
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def is_active(self):  # Flask-Login hook
        return self.is_active_account

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > utcnow())

    @property
    def first_name(self):
        return self.full_name.split()[0]

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class MaintenanceRequest(db.Model):
    __tablename__ = "maintenance_requests"
    __table_args__ = (
        CheckConstraint("priority IN ('Low','Medium','High','Critical')", name="ck_req_priority"),
        CheckConstraint("requested_priority IN ('Low','Medium','High','Critical')", name="ck_req_reqprio"),
        CheckConstraint(
            "status IN ('Submitted','Under Review','Assigned','In Progress','Resolved','Closed','Rejected')",
            name="ck_req_status"),
        Index("ix_req_status_priority", "status", "priority"),
        Index("ix_req_duplicate_lookup", "building", "category", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reference_id = db.Column(db.String(20), nullable=False, unique=True, index=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    building = db.Column(db.String(60), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    requested_priority = db.Column(db.String(10), nullable=False)   # what the reporter chose
    priority = db.Column(db.String(10), nullable=False)             # effective priority
    status = db.Column(db.String(20), nullable=False, default="Submitted")
    image_filename = db.Column(db.String(100))
    resolution_notes = db.Column(db.Text)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    duplicate_of_id = db.Column(db.Integer, db.ForeignKey("maintenance_requests.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    due_at = db.Column(db.DateTime, nullable=False)
    resolved_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)

    requester = db.relationship("User", foreign_keys=[requester_id], backref="requests")
    duplicate_of = db.relationship("MaintenanceRequest", remote_side=[id])
    assignments = db.relationship("RequestAssignment", backref="request", order_by="RequestAssignment.assigned_at",
                                  cascade="all, delete-orphan")
    updates = db.relationship("RequestUpdate", backref="request", order_by="RequestUpdate.created_at, RequestUpdate.id",
                              cascade="all, delete-orphan")
    feedback = db.relationship("Feedback", backref="request", uselist=False, cascade="all, delete-orphan")

    @property
    def current_assignment(self):
        for a in reversed(self.assignments):
            if a.is_active:
                return a
        return None

    @property
    def assigned_staff(self):
        a = self.current_assignment
        return a.staff if a else None

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    @property
    def is_overdue(self):
        return self.is_open and self.due_at < utcnow()

    @property
    def priority_escalated(self):
        return self.priority != self.requested_priority

    @property
    def hours_to_resolve(self):
        if self.resolved_at:
            return round((self.resolved_at - self.created_at).total_seconds() / 3600, 1)
        return None


class RequestAssignment(db.Model):
    __tablename__ = "request_assignments"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("maintenance_requests.id"), nullable=False, index=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    note = db.Column(db.String(255))

    staff = db.relationship("User", foreign_keys=[staff_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])


class RequestUpdate(db.Model):
    """Immutable history of status changes, assignments and priority changes."""
    __tablename__ = "request_updates"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("maintenance_requests.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_type = db.Column(db.String(20), nullable=False, default="status")
    from_status = db.Column(db.String(20))
    to_status = db.Column(db.String(20))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    author = db.relationship("User")


class Feedback(db.Model):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),)
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("maintenance_requests.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))      # NULL for failed logins of unknown users
    action = db.Column(db.String(40), nullable=False, index=True)
    entity_type = db.Column(db.String(30))
    entity_id = db.Column(db.String(30))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    user = db.relationship("User")
