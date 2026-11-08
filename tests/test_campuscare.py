import io
from datetime import timedelta

import pytest

from campuscare.extensions import db
from campuscare.models import AuditLog, MaintenanceRequest, RequestAssignment, User, utcnow
from campuscare import services as svc
from campuscare.services import PermissionDenied, ValidationError, WorkflowError, DuplicateFound
from conftest import JPG, PNG, VALID_FORM, login, png_file


def make_request(users, **over):
    form = {**VALID_FORM, **over}
    return svc.create_request(db.session.get(User, users["student"]), form)


def get(model, ident):
    return db.session.get(model, ident)


def to_assigned(users, req, staff_key="staff"):
    admin = get(User, users["admin"])
    svc.transition(req, admin, "Under Review")
    svc.assign(req, admin, users[staff_key], "go")
    return req


# ------------------------------------------------------------------ authentication & authorisation
def test_tc01_valid_login_redirects_to_role_dashboard(client, users, record):
    r = login(client, "student")
    record("TC-01", f"HTTP {r.status_code}, redirected to {r.headers['Location']}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    assert client.get("/dashboard").status_code == 200


def test_tc02_invalid_password_rejected_with_generic_message(client, users, record):
    r = login(client, "student", "wrong-pass1")
    record("TC-02", f"HTTP {r.status_code}; generic error shown; no session created")
    assert r.status_code == 401 and b"Invalid email or password" in r.data
    assert client.get("/dashboard").status_code == 302     # still anonymous


def test_tc03_account_locks_after_repeated_failures(client, users, record):
    for _ in range(5):
        login(client, "student", "bad-pass1")
    r = login(client, "student")          # correct password, but locked
    user = get(User, users["student"])
    record("TC-03", f"After 5 failures correct password gives HTTP {r.status_code}; locked_until set={user.locked_until is not None}")
    assert r.status_code == 401 and user.is_locked()


def test_tc04_self_registration_cannot_create_privileged_role(client, app, record):
    r = client.post("/register", data={"full_name": "Eve Hacker", "email": "eve@t.test", "password": "Passw0rd!",
                                       "confirm_password": "Passw0rd!", "role": "admin"})
    u = User.query.filter_by(email="eve@t.test").first()
    record("TC-04", f"Account created with role='{u.role}' although role=admin was posted")
    assert r.status_code == 302 and u.role == "requester"


def test_tc05_weak_password_rejected_on_registration(client, app, record):
    r = client.post("/register", data={"full_name": "Weak User", "email": "weak@t.test", "password": "abc",
                                       "confirm_password": "abc"})
    record("TC-05", f"HTTP {r.status_code}; user created={User.query.filter_by(email='weak@t.test').first() is not None}")
    assert r.status_code == 422 and User.query.filter_by(email="weak@t.test").first() is None


def test_tc06_anonymous_user_redirected_to_login(client, record):
    r = client.get("/dashboard")
    record("TC-06", f"HTTP {r.status_code} → {r.headers['Location']}")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_tc07_student_cannot_open_admin_pages(as_user, record):
    c = as_user("student")
    codes = [c.get(p).status_code for p in ("/admin/dashboard", "/admin/users", "/admin/reports", "/admin/audit")]
    record("TC-07", f"HTTP codes for 4 admin URLs: {codes}")
    assert codes == [403, 403, 403, 403]


def test_tc08_staff_cannot_manage_users_or_assign(as_user, users, record):
    req = make_request(users)
    c = as_user("staff")
    a = c.get("/admin/users").status_code
    b = c.post(f"/admin/requests/{req.reference_id}/assign", data={"staff_id": users["staff"]}).status_code
    record("TC-08", f"/admin/users → {a}; POST assign → {b}")
    assert a == 403 and b == 403


def test_tc09_student_cannot_view_another_students_request(as_user, users, record):
    req = make_request(users)
    c = as_user("student2")
    r = c.get(f"/requests/{req.reference_id}")
    record("TC-09", f"HTTP {r.status_code} for another user's request")
    assert r.status_code == 403


def test_tc10_csrf_token_required_when_enabled(app, users, record):
    app.config["CSRF_ENABLED"] = True
    c = app.test_client()
    r = c.post("/login", data={"email": "student@t.test", "password": "Passw0rd!"})
    record("TC-10", f"POST without CSRF token → HTTP {r.status_code}")
    assert r.status_code == 400


# ------------------------------------------------------------------ request submission & validation
def test_tc11_valid_request_created_with_reference_and_history(as_user, users, record):
    c = as_user("student")
    r = c.post("/requests/new", data=VALID_FORM)
    req = MaintenanceRequest.query.one()
    record("TC-11", f"HTTP {r.status_code}; ref={req.reference_id}; status={req.status}; history rows={len(req.updates)}")
    assert r.status_code == 302 and req.status == "Submitted" and req.reference_id.startswith("CC-")
    assert len(req.updates) == 1 and AuditLog.query.filter_by(action="REQUEST_CREATE").count() == 1


def test_tc12_missing_required_fields_rejected(as_user, record):
    c = as_user("student")
    r = c.post("/requests/new", data={"title": "", "description": "short", "category": "", "building": "", "location": "", "priority": ""})
    record("TC-12", f"HTTP {r.status_code}; rows created={MaintenanceRequest.query.count()}")
    assert r.status_code == 422 and MaintenanceRequest.query.count() == 0 and b"Title is required" in r.data


def test_tc13_safety_keyword_escalates_to_critical(users, record):
    req = make_request(users, title="Sparking socket", description="Wall socket produces sparks and a burning smell.", priority="Low", category="Electrical")
    record("TC-13", f"Requested={req.requested_priority}, effective={req.priority}, due in {(req.due_at-req.created_at).total_seconds()/3600:.0f} h")
    assert req.priority == "Critical" and req.requested_priority == "Low"
    assert (req.due_at - req.created_at) == timedelta(hours=8)


def test_tc14_safety_category_minimum_priority_high_but_extinguisher_not_critical(users, record):
    req = make_request(users, title="Fire extinguisher gauge in red", description="Pressure gauge outside Room 101 shows red zone.",
                       category="Safety & Security", priority="Low", location="Corridor")
    record("TC-14", f"Requested=Low, effective={req.priority}")
    assert req.priority == "High"


def test_tc15_duplicate_detected_and_blocked_until_confirmed(users, record):
    first = make_request(users)
    with pytest.raises(DuplicateFound) as exc:
        make_request(users, title="Projector flickering", location="lab 3 ")
    second = svc.create_request(get(User, users["student2"]), {**VALID_FORM, "title": "Projector flickering"}, confirm_duplicate=True)
    record("TC-15", f"Duplicate warning listed {exc.value.duplicates[0].reference_id}; confirmed copy flagged duplicate_of={second.duplicate_of.reference_id}")
    assert exc.value.duplicates[0].id == first.id and second.duplicate_of_id == first.id


def test_tc16_non_duplicate_in_other_location_accepted(users, record):
    make_request(users)
    other = make_request(users, location="Lab 5")
    record("TC-16", f"Different room accepted: {other.reference_id}, duplicate_of={other.duplicate_of_id}")
    assert other.duplicate_of_id is None


# ------------------------------------------------------------------ image upload
def test_tc17_valid_png_upload_stored_and_access_controlled(as_user, users, record):
    c = as_user("student")
    c.post("/requests/new", data={**VALID_FORM, "image": png_file()}, content_type="multipart/form-data")
    req = MaintenanceRequest.query.one()
    own = c.get(f"/uploads/{req.image_filename}").status_code
    other = as_user("student2").get(f"/uploads/{req.image_filename}").status_code
    record("TC-17", f"Stored as random name {req.image_filename}; owner → {own}; other student → {other}")
    assert req.image_filename.endswith(".png") and req.image_filename != "photo.png" and own == 200 and other == 403


@pytest.mark.parametrize("name,data", [("evil.exe", b"MZ" + b"0" * 50), ("note.png", b"this is not an image"), ("a.jpg", PNG)])
def test_tc18_invalid_uploads_rejected(as_user, record, name, data):
    c = as_user("student")
    r = c.post("/requests/new", data={**VALID_FORM, "image": (io.BytesIO(data), name)}, content_type="multipart/form-data")
    record("TC-18", f"{name}: HTTP {r.status_code}; requests created={MaintenanceRequest.query.count()}")
    assert r.status_code == 422 and MaintenanceRequest.query.count() == 0


def test_tc19_oversized_image_rejected(as_user, record):
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024 + 10)
    c = as_user("student")
    r = c.post("/requests/new", data={**VALID_FORM, "image": (io.BytesIO(big), "big.png")}, content_type="multipart/form-data")
    record("TC-19", f"2 MB+ image: HTTP {r.status_code}")
    assert r.status_code == 422 and b"too large" in r.data


# ------------------------------------------------------------------ workflow
def test_tc20_admin_review_then_assign_records_assignment_and_audit(as_user, users, record):
    req = make_request(users)
    admin = as_user("admin")
    admin.post(f"/requests/{req.reference_id}/transition", data={"to_status": "Under Review"})
    r = admin.post(f"/admin/requests/{req.reference_id}/assign", data={"staff_id": users["staff"], "note": "Check wiring"})
    req = get(MaintenanceRequest, req.id)
    record("TC-20", f"HTTP {r.status_code}; status={req.status}; assigned_to={req.assigned_staff.full_name}; history={len(req.updates)}; audit ASSIGN={AuditLog.query.filter_by(action='ASSIGN').count()}")
    assert req.status == "Assigned" and req.assigned_staff.id == users["staff"] and AuditLog.query.filter_by(action="ASSIGN").count() == 1


def test_tc21_invalid_transition_rejected_at_service_and_http_level(as_user, users, record):
    req = make_request(users)
    admin = get(User, users["admin"])
    with pytest.raises(WorkflowError):
        svc.transition(req, admin, "Closed")
    with pytest.raises(WorkflowError):
        svc.transition(req, admin, "Assigned")          # must go through assign()
    r = as_user("admin").post(f"/requests/{req.reference_id}/transition", data={"to_status": "Resolved"}, follow_redirects=True)
    req = get(MaintenanceRequest, req.id)
    record("TC-21", f"Submitted→Closed, Submitted→Assigned, Submitted→Resolved all refused; status still {req.status}; message shown={b'Invalid transition' in r.data}")
    assert req.status == "Submitted" and b"Invalid transition" in r.data


def test_tc22_assignment_requires_review_and_valid_staff(users, record):
    req = make_request(users)
    admin = get(User, users["admin"])
    with pytest.raises(WorkflowError):
        svc.assign(req, admin, users["staff"])                 # still Submitted
    svc.transition(req, admin, "Under Review")
    with pytest.raises(WorkflowError):
        svc.assign(req, admin, users["student"])               # not a staff member
    record("TC-22", "Assign refused while Submitted; refused for a student account; status unchanged")
    assert req.status == "Under Review" and req.assigned_staff is None


def test_tc23_staff_cannot_resolve_task_assigned_to_someone_else(users, record):
    req = to_assigned(users, make_request(users), "staff")
    other = get(User, users["staff2"])
    with pytest.raises(PermissionDenied):
        svc.transition(req, other, "In Progress")
    svc.transition(req, get(User, users["staff"]), "In Progress")
    with pytest.raises(PermissionDenied):
        svc.transition(req, other, "Resolved", "Trying to resolve someone else's task")
    record("TC-23", "Unassigned staff blocked from Start and Resolve with PermissionDenied")
    assert req.status == "In Progress"


def test_tc24_resolution_requires_notes(users, record):
    req = to_assigned(users, make_request(users))
    staff = get(User, users["staff"])
    svc.transition(req, staff, "In Progress")
    with pytest.raises(WorkflowError):
        svc.transition(req, staff, "Resolved", "ok")
    svc.transition(req, staff, "Resolved", "Replaced the lamp and tested.")
    record("TC-24", f"Note 'ok' refused; full note accepted; status={req.status}; resolved_at set={req.resolved_at is not None}")
    assert req.status == "Resolved" and req.resolved_at


def test_tc25_full_lifecycle_through_web_interface(as_user, users, record):
    student, admin, staff = as_user("student"), as_user("admin"), as_user("staff")
    student.post("/requests/new", data=VALID_FORM)
    ref = MaintenanceRequest.query.one().reference_id
    admin.post(f"/requests/{ref}/transition", data={"to_status": "Under Review"})
    admin.post(f"/admin/requests/{ref}/assign", data={"staff_id": users["staff"]})
    staff.post(f"/requests/{ref}/transition", data={"to_status": "In Progress"})
    staff.post(f"/requests/{ref}/transition", data={"to_status": "Resolved", "note": "Replaced projector lamp and tested."})
    student.post(f"/requests/{ref}/transition", data={"to_status": "Closed"})
    req = MaintenanceRequest.query.one()
    path = " → ".join([req.updates[0].to_status] + [u.to_status for u in req.updates[1:] if u.event_type != "priority"])
    record("TC-25", f"Final status {req.status}; path: {path}")
    assert req.status == "Closed" and req.closed_at


def test_tc26_reject_requires_reason_and_is_terminal(users, record):
    req = make_request(users)
    admin = get(User, users["admin"])
    svc.transition(req, admin, "Under Review")
    with pytest.raises(WorkflowError):
        svc.transition(req, admin, "Rejected", "")
    svc.transition(req, admin, "Rejected", "Covered by annual maintenance plan")
    with pytest.raises(WorkflowError):
        svc.transition(req, admin, "Under Review")
    record("TC-26", "Reject without reason refused; with reason accepted; no transitions out of Rejected")
    assert req.status == "Rejected"


def test_tc27_reopen_resolved_request_needs_explanation(users, record):
    req = to_assigned(users, make_request(users))
    staff, student = get(User, users["staff"]), get(User, users["student"])
    svc.transition(req, staff, "In Progress"); svc.transition(req, staff, "Resolved", "Replaced the lamp.")
    with pytest.raises(WorkflowError):
        svc.transition(req, student, "In Progress", "")
    svc.transition(req, student, "In Progress", "Still not working after the repair")
    record("TC-27", f"Re-open accepted with reason; status={req.status}; resolved_at cleared={req.resolved_at is None}")
    assert req.status == "In Progress" and req.resolved_at is None


# ------------------------------------------------------------------ feedback
def test_tc28_feedback_only_after_resolution_once_and_valid_rating(users, record):
    req = to_assigned(users, make_request(users))
    student = get(User, users["student"])
    with pytest.raises(WorkflowError):
        svc.submit_feedback(req, student, 5, "too early")
    staff = get(User, users["staff"])
    svc.transition(req, staff, "In Progress"); svc.transition(req, staff, "Resolved", "Replaced the lamp.")
    with pytest.raises(ValidationError):
        svc.submit_feedback(req, student, 9, "")
    with pytest.raises(PermissionDenied):
        svc.submit_feedback(req, get(User, users["student2"]), 5, "not mine")
    svc.submit_feedback(req, student, 4, "Good")
    with pytest.raises(WorkflowError):
        svc.submit_feedback(req, student, 5, "again")
    record("TC-28", f"Early, out-of-range, foreign and duplicate feedback refused; stored rating={req.feedback.rating}")
    assert req.feedback.rating == 4


# ------------------------------------------------------------------ filtering, overdue, reports, priority
def test_tc29_filters_return_expected_subset(as_user, users, record):
    make_request(users, category="Electrical", location="Room 1", priority="High")
    make_request(users, category="Plumbing & Water", location="Room 2", priority="Low")
    make_request(users, category="Electrical", location="Room 3", priority="Low", title="Fan noisy in room")
    admin = as_user("admin")
    def count(qs):
        return admin.get("/admin/requests?" + qs).data.count(b"class=\"ref\"")
    a, b, c, d = count("category=Electrical"), count("priority=Low"), count("category=Electrical&priority=Low"), count("q=Fan")
    record("TC-29", f"category=Electrical→{a}; priority=Low→{b}; both→{c}; search 'Fan'→{d}")
    assert (a, b, c, d) == (2, 2, 1, 1)


def test_tc30_overdue_detection_and_priority_sorting(users, record):
    low = make_request(users, location="Room 1", priority="Low")
    crit = make_request(users, location="Room 2", priority="High", title="Smoke from ceiling", description="There is smoke coming from the ceiling panel.")
    low.due_at = utcnow() - timedelta(hours=1); db.session.commit()
    ordered = svc.apply_filters(MaintenanceRequest.query, {"sort": "priority"}).all()
    overdue = svc.apply_filters(MaintenanceRequest.query, {"overdue": "1"}).all()
    record("TC-30", f"Priority order: {[r.priority for r in ordered]}; overdue list: {[r.reference_id for r in overdue]}")
    assert ordered[0].id == crit.id and [r.id for r in overdue] == [low.id] and low.is_overdue and not crit.is_overdue


def test_tc31_admin_priority_change_requires_reason_and_resets_due_date(users, record):
    req = make_request(users, priority="Low")
    admin = get(User, users["admin"])
    with pytest.raises(WorkflowError):
        svc.change_priority(req, admin, "High", "")
    old_due = req.due_at
    svc.change_priority(req, admin, "High", "Affects exam preparation")
    record("TC-31", f"Priority Low→{req.priority}; due moved from +168h to +{(req.due_at-req.created_at).total_seconds()/3600:.0f}h")
    assert req.priority == "High" and req.due_at < old_due


def test_tc32_report_summary_and_csv_export(as_user, users, record):
    req = to_assigned(users, make_request(users))
    staff = get(User, users["staff"])
    svc.transition(req, staff, "In Progress"); svc.transition(req, staff, "Resolved", "Replaced the lamp.")
    make_request(users, location="Room 9")
    s = svc.report_summary()
    r = as_user("admin").get("/admin/reports.csv")
    lines = r.data.decode().strip().splitlines()
    record("TC-32", f"Report: total={s['total']}, resolved={s['resolved']}; CSV HTTP {r.status_code}, {len(lines)-1} data rows, type={r.mimetype}")
    assert s["total"] == 2 and s["resolved"] == 1 and len(lines) == 3 and r.mimetype == "text/csv"


def test_tc33_suggest_staff_prefers_specialty_then_lowest_workload(users, record):
    req = make_request(users, category="Electrical", location="Room 7")
    ranked = svc.suggest_staff("Electrical")
    record("TC-33", f"Ranking for Electrical: {[(r['user'].full_name, r['match'], r['open_tasks']) for r in ranked]}")
    assert ranked[0]["user"].id == users["staff"] and ranked[0]["match"] is True


def test_tc34_deactivated_user_cannot_login(client, users, record):
    u = get(User, users["student"]); u.is_active_account = False; db.session.commit()
    r = login(client, "student")
    record("TC-34", f"Deactivated account login → HTTP {r.status_code}")
    assert r.status_code == 401


def test_tc35_admin_cannot_demote_or_deactivate_self(as_user, users, record):
    c = as_user("admin")
    c.post(f"/admin/users/{users['admin']}/update", data={"role": "requester", "toggle_active": "1"})
    u = get(User, users["admin"])
    record("TC-35", f"Own role after attempt: {u.role}; active={u.is_active_account}")
    assert u.role == "admin" and u.is_active_account
