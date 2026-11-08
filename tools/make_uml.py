"""Generate all UML diagrams:  python tools/make_uml.py   ->  docs/uml/*.png and *.drawio"""
import os
from umlkit import Diagram, LIGHT, BLUE

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "uml")
os.makedirs(OUT, exist_ok=True)


def save(d, name):
    d.png(os.path.join(OUT, name + ".png"))
    d.drawio(os.path.join(OUT, name + ".drawio"))
    print("wrote", name)


# ============================================================================ 1. USE CASE
def use_case():
    d = Diagram("CampusCare Use Case Diagram", 1560, 1010)
    d.region(235, 30, 1090, 950, "CampusCare system boundary")
    d.actor("req", 90, 250, "Student /\nFaculty")
    d.actor("stf", 90, 640, "Maintenance\nStaff")
    d.actor("adm", 1450, 440, "Administrator")
    U = lambda k, x, y, t, w=230, h=62: d.ellipse(k, x, y, w, h, t)
    # column A: requester + staff
    U("submit", 300, 110, "Submit Maintenance\nRequest")
    U("track", 300, 215, "Track Request Status")
    U("feed", 300, 320, "Give Feedback")
    U("close", 300, 425, "Confirm & Close /\nRe-open Request")
    U("tasks", 300, 590, "View Assigned Tasks")
    U("update", 300, 695, "Update Task Status")
    U("hist", 300, 800, "View Task History")
    # column B: included / extending behaviour
    U("dup", 640, 80, "Detect Duplicate\nRequest", w=200)
    U("valid", 640, 175, "Validate Input", w=200)
    U("img", 640, 270, "Upload Supporting\nImage", w=200)
    U("notes", 640, 695, "Add Resolution\nNotes", w=200)
    U("login", 590, 890, "Log in / Log out\n(role-based access)", w=250, h=66)
    # column C: administrator
    for i, (k, t) in enumerate([("triage", "Review & Triage Request"), ("assign", "Assign Request to Staff"),
                                ("prio", "Change Priority"), ("filt", "Filter & Search Requests"),
                                ("dash", "View Dashboard Statistics"), ("rep", "Generate Reports"),
                                ("users", "Manage Users"), ("audit", "View Audit Log")]):
        U(k, 975, 85 + i * 100, t, w=270)
    d.edge("dup", "submit", "«include»", "include", lbl_off=(0, -10))
    d.edge("valid", "submit", "«include»", "include", lbl_off=(0, -10))
    d.edge("img", "submit", "«extend»", "extend", lbl_off=(0, 12))
    d.edge("notes", "update", "«include»", "include")
    for a, b in [("req", "submit"), ("req", "track"), ("req", "feed"), ("req", "close"), ("stf", "tasks"), ("stf", "update"), ("stf", "hist"),
                 ("req", "login"), ("stf", "login"), ("adm", "login")]:
        d.edge(a, b, kind="assoc")
    for k in ("triage", "assign", "prio", "filt", "dash", "rep", "users", "audit"):
        d.edge("adm", k, kind="assoc")
    d.edge("adm", "track", kind="assoc", pts=[(870, 40), (480, 40)]) if False else None
    d.note(255, 905, 310, 55, "All roles must authenticate. Authorisation is\nenforced per use case (RBAC).", fs=9)
    save(d, "01_use_case_diagram")


# ============================================================================ 2. CLASS
def class_diagram():
    d = Diagram("CampusCare Class Diagram", 1780, 1250); d.fscale = 1.1
    d.region(20, 15, 1740, 215, "Presentation layer — Flask blueprints (campuscare/routes)")
    d.region(20, 250, 1740, 225, "Business layer — campuscare/services.py (framework-independent rules)")
    d.region(20, 495, 1740, 735, "Persistence layer — SQLAlchemy models (campuscare/models.py) → SQLite")
    d.cls("auth", 40, 45, "AuthRoutes", [], ["login()", "register()", "logout()"], "«blueprint auth»", w=235)
    d.cls("main", 330, 45, "MainRoutes", [], ["dashboard()  new_request()", "my_requests()  detail(ref)", "do_transition(ref)  feedback(ref)", "api_duplicates()  uploaded_file()"], "«blueprint main»", w=330)
    d.cls("staff", 715, 45, "StaffRoutes", [], ["dashboard()", "history()"], "«blueprint staff»", w=235)
    d.cls("admin", 1005, 45, "AdminRoutes", [], ["dashboard()  requests_list()", "assign_request()  priority()", "users()  new_user()  update_user()", "reports()  reports_csv()  audit_log()"], "«blueprint admin»", w=360)
    d.cls("rbac", 1420, 45, "RBAC / Security", [], ["role_required(*roles)", "csrf_protect()", "security headers"], "«decorator / hooks»", w=310)
    d.cls("svc", 40, 285, "RequestService", [], ["create_request(user, form, file)", "transition(req, actor, to, note)", "assign(req, admin, staff_id, note)", "change_priority(req, admin, p, why)", "submit_feedback(req, user, rating)", "find_duplicates()  escalate_priority()", "audit(user, action, entity, id)"], "«service»", w=380)
    d.cls("pol", 520, 300, "WorkflowPolicy", ["TRANSITIONS: {(from,to): roles}", "SLA_HOURS: {priority: hours}"], [], "«policy»", w=330)
    d.cls("svc2", 1005, 285, "QueryService", [], ["apply_filters(query, args)", "dashboard_stats()", "report_summary()  report_csv()", "suggest_staff(category)", "available_actions(req, user)", "can_view(req, user)"], "«service»", w=330)
    d.cls("user", 40, 540, "User", ["id: int  PK", "full_name: str", "email: str  UNIQUE", "password_hash: str", "role: requester|staff|admin", "department, specialty: str", "is_active_account: bool", "failed_attempts: int", "locked_until: datetime"], ["set_password(raw)", "check_password(raw)", "is_locked()"], w=300)
    d.cls("log", 40, 960, "AuditLog", ["id: int  PK", "user_id: int  FK→User (nullable)", "action: str  INDEX", "entity_type, entity_id: str", "details: text", "ip_address: str", "created_at: datetime"], [], w=300)
    d.cls("req", 450, 540, "MaintenanceRequest", ["id: int  PK", "reference_id: str  UNIQUE", "title, description: str", "category, building, location", "requested_priority, priority", "status: str", "image_filename: str", "requester_id: int  FK→User", "duplicate_of_id: int  FK→self", "created_at, due_at, resolved_at"], ["current_assignment", "assigned_staff", "is_open", "is_overdue", "hours_to_resolve"], w=330)
    d.cls("asg", 940, 540, "RequestAssignment", ["id: int  PK", "request_id: int  FK", "staff_id: int  FK→User", "assigned_by_id: int  FK→User", "assigned_at: datetime", "is_active: bool", "note: str"], [], w=330)
    d.cls("upd", 940, 790, "RequestUpdate", ["id: int  PK", "request_id: int  FK", "author_id: int  FK→User", "event_type: status|assignment|priority", "from_status, to_status: str", "note: str", "created_at: datetime"], [], w=370)
    d.cls("fb", 940, 1040, "Feedback", ["id: int  PK", "request_id: int  FK  UNIQUE", "user_id: int  FK→User", "rating: int  CHECK 1..5", "comment: str", "created_at: datetime"], [], w=330)
    for a, b in (("auth", "svc"), ("main", "svc"), ("staff", "svc2"), ("admin", "svc2")):
        d.edge(a, b, "uses", "dep", lbl_off=(0, 0))
    d.edge("rbac", "admin", "guards", "dep", lbl_off=(0, -10))
    d.edge("svc", "pol", "enforces", "dep", lbl_off=(0, -10))
    d.edge("svc", "req", "reads / writes", "dep", lbl_off=(-10, 10))
    d.edge("user", "req", "reports", "assoc", a_lbl="1", b_lbl="0..*", lbl_off=(0, -10))
    d.edge("req", "asg", "assigned via", "compose", b_lbl="0..*", lbl_off=(0, -10))
    d.edge("req", "upd", "history", "compose", b_lbl="1..*", lbl_off=(0, 12))
    d.edge("req", "fb", "feedback", "assoc", a_lbl="1", b_lbl="0..1", lbl_off=(0, 14))
    d.edge("user", "log", "acts", "assoc", a_lbl="1", b_lbl="0..*", lbl_off=(30, 0))
    d.note(450, 1010, 410, 95, "Every staff_id, assigned_by_id, author_id, user_id and\nrequester_id points to User. services.audit() writes one\nAuditLog row for each state-changing action.", fs=9)
    d.note(1360, 540, 380, 110, "MaintenanceRequest.duplicate_of_id is a\nself-reference: set when the reporter\nacknowledged a similar open request.", fs=9)
    save(d, "02_class_diagram")
    from PIL import Image
    im = Image.open(os.path.join(OUT, "02_class_diagram.png")); k = im.width / d.w
    im.crop((0, 0, im.width, int(480 * k))).save(os.path.join(OUT, "02a_class_layers.png"))
    im.crop((0, int(488 * k), im.width, im.height)).save(os.path.join(OUT, "02b_class_persistence.png"))


# ============================================================================ 3. SEQUENCE
def sequence():
    d = Diagram("CampusCare Sequence Diagram — submit and assign a request", 1560, 1260); d.fscale = 1.15
    xs = dict(stu=150, rt=500, sv=900, db=1250, adm=1470)
    d.lifeline("stu", xs["stu"], 20, 200, 1210, "Student / Faculty\n(browser)")
    d.lifeline("rt", xs["rt"], 20, 200, 1210, ":Routes\n«Flask blueprint»")
    d.lifeline("sv", xs["sv"], 20, 200, 1210, ":RequestService\n«services.py»")
    d.lifeline("db", xs["db"], 20, 200, 1210, ":Database\n«SQLite via SQLAlchemy»")
    d.lifeline("adm", xs["adm"], 20, 170, 1210, "Administrator\n(browser)")
    d.label(30, 100, "A. Submit request", 12, True, BLUE)
    y = 130
    d.msg(xs["stu"], xs["rt"], y, "1: POST /requests/new (form + image, CSRF token)"); y += 45
    d.msg(xs["rt"], xs["sv"], y, "2: create_request(user, form, image)"); y += 40
    d.msg(xs["sv"], xs["sv"], y, "3: clean_request_form(); validate_image()", selfcall=True); y += 52
    d.msg(xs["sv"], xs["db"], y, "4: find_duplicates(building, location, category)"); y += 40
    d.msg(xs["db"], xs["sv"], y, "5: open requests at same place", dashed=True); y += 30
    d.frame(260, y, 1100, 330, "alt", divider=y + 118, divider_text="[no duplicate, or reporter confirmed “different problem”]")
    d.label(275, y + 40, "[possible duplicate and not confirmed]", 9.5, False, "#475569")
    y += 78
    d.msg(xs["sv"], xs["rt"], y - 8, "6: raise DuplicateFound(matches)", dashed=True); y += 33
    d.msg(xs["rt"], xs["stu"], y - 12, "7: 409 form + warning with existing request links", dashed=True); y += 64
    d.msg(xs["sv"], xs["sv"], y, "8: escalate_priority(); set due_at from SLA", selfcall=True); y += 52
    d.msg(xs["sv"], xs["db"], y, "9: INSERT request, history row, audit log; COMMIT"); y += 42
    d.msg(xs["sv"], xs["rt"], y, "10: MaintenanceRequest (CC-2026-nnnn, Submitted)", dashed=True); y += 42
    d.msg(xs["rt"], xs["stu"], y, "11: 302 redirect → request detail page", dashed=True); y += 40
    y += 40
    d.cropY = y - 20
    d.label(30, y, "B. Review and assign", 12, True, BLUE); y += 36
    d.msg(xs["adm"], xs["rt"], y, "12: POST /requests/{ref}/transition (Under Review)"); y += 42
    d.msg(xs["rt"], xs["sv"], y, "13: transition(req, admin, 'Under Review')"); y += 40
    d.msg(xs["sv"], xs["sv"], y, "14: check TRANSITIONS, role, ownership", selfcall=True); y += 52
    d.msg(xs["sv"], xs["db"], y, "15: UPDATE status; INSERT history + audit"); y += 50
    d.msg(xs["adm"], xs["rt"], y, "16: POST /admin/requests/{ref}/assign (staff_id)"); y += 42
    d.msg(xs["rt"], xs["sv"], y, "17: assign(req, admin, staff_id, note)"); y += 40
    d.msg(xs["sv"], xs["sv"], y, "18: staff active & role == staff? status Under Review?", selfcall=True); y += 52
    d.msg(xs["sv"], xs["db"], y, "19: INSERT assignment; status=Assigned; history+audit"); y += 42
    d.msg(xs["sv"], xs["rt"], y, "20: updated request", dashed=True); y += 40
    d.msg(xs["rt"], xs["adm"], y, "21: 302 redirect → detail (shows assigned staff)", dashed=True); y += 30
    d.h = int(y + 50)
    save(d, "03_sequence_diagram")
    from PIL import Image
    im = Image.open(os.path.join(OUT, "03_sequence_diagram.png")); k = im.width / d.w
    top = im.crop((0, 0, im.width, int(d.cropY * k)))
    strip = im.crop((0, 0, im.width, int(80 * k)))
    bot = im.crop((0, int(d.cropY * k), im.width, im.height))
    b = Image.new("RGB", (im.width, strip.height + bot.height), "white"); b.paste(strip, (0, 0)); b.paste(bot, (0, strip.height))
    top.save(os.path.join(OUT, "03a_sequence_submit.png")); b.save(os.path.join(OUT, "03b_sequence_review_assign.png"))


# ============================================================================ 4. ER
def er():
    d = Diagram("CampusCare ER Diagram", 1700, 820); d.fscale = 1.1
    def table(k, x, y, name, cols, w=330):
        d.cls(k, x, y, name, cols, [], w=w, header="#dbeafe")
    table("users", 40, 60, "users", ["PK id             INTEGER", "   full_name      VARCHAR(100) NN", "UQ email          VARCHAR(120) NN", "   password_hash  VARCHAR(255) NN", "   role           VARCHAR(20)  NN CHECK", "   department     VARCHAR(100)", "   specialty      VARCHAR(50)", "   is_active_account BOOLEAN NN", "   failed_attempts INTEGER NN", "   locked_until   DATETIME", "   created_at     DATETIME NN"], w=360)
    table("req", 640, 60, "maintenance_requests", ["PK id               INTEGER", "UQ reference_id      VARCHAR(20) NN", "   title, description TEXT NN", "IX category           VARCHAR(40) NN", "   building, location VARCHAR NN", "   requested_priority VARCHAR(10) NN", "   priority           VARCHAR(10) NN CHECK", "   status             VARCHAR(20) NN CHECK", "   image_filename     VARCHAR(100)", "   resolution_notes   TEXT", "FK requester_id       → users.id NN", "FK duplicate_of_id    → requests.id", "   created_at, updated_at, due_at NN", "   resolved_at, closed_at DATETIME"], w=380)
    table("asg", 1240, 40, "request_assignments", ["PK id            INTEGER", "FK request_id    → requests.id NN", "FK staff_id      → users.id NN", "FK assigned_by_id→ users.id NN", "   assigned_at   DATETIME NN", "   is_active     BOOLEAN NN", "   note          VARCHAR(255)"], w=380)
    table("upd", 1240, 330, "request_updates", ["PK id          INTEGER", "FK request_id  → requests.id NN", "FK author_id   → users.id NN", "   event_type  VARCHAR(20) NN", "   from_status VARCHAR(20)", "   to_status   VARCHAR(20)", "   note        TEXT", "   created_at  DATETIME NN"], w=380)
    table("fb", 1240, 640, "feedback", ["PK id          INTEGER", "FK,UQ request_id → requests.id NN", "FK user_id     → users.id NN", "   rating      INTEGER NN CHECK 1..5", "   comment     VARCHAR(500)", "   created_at  DATETIME NN"], w=380)
    table("log", 40, 560, "audit_logs", ["PK id           INTEGER", "FK user_id      → users.id (NULL ok)", "IX action        VARCHAR(40) NN", "IX entity_type, entity_id VARCHAR", "   details       TEXT", "   ip_address    VARCHAR(45)", "IX created_at    DATETIME NN"], w=380)
    d.edge("users", "req", "reports", "assoc", a_lbl="1", b_lbl="N", lbl_off=(0, -12))
    d.edge("req", "asg", "has", "assoc", a_lbl="1", b_lbl="N", lbl_off=(0, -12))
    d.edge("req", "upd", "history", "assoc", a_lbl="1", b_lbl="N", lbl_off=(0, 14))
    d.edge("req", "fb", "rated by", "assoc", a_lbl="1", b_lbl="0..1", lbl_off=(0, 14))
    d.edge("users", "log", "performs", "assoc", a_lbl="1", b_lbl="N", lbl_off=(30, 0))
    d.edge("users", "asg", "staff / assigner", "assoc", pts=[(220, 28), (1430, 28)], a_lbl="1", b_lbl="N", lbl_off=(0, -10))
    d.note(640, 700, 460, 120, "Normalisation (3NF): reporter, staff and administrator details live only in\nusers; assignments, status history and feedback are separate tables so\nre-assignment and re-opening never overwrite earlier facts. Current\nassignee = the single row with is_active = TRUE for the request.", fs=9.5)
    save(d, "04_er_diagram")


# ============================================================================ 5. ARCHITECTURE
def architecture():
    d = Diagram("CampusCare System Architecture", 1500, 830)
    d.region(40, 40, 1420, 120, "Client tier — any modern browser")
    d.box("b1", 80, 80, 300, 60, "HTML5 templates (Jinja2)\nBootstrap 5 · responsive layout", fill="#ffffff")
    d.box("b2", 440, 80, 300, 60, "JavaScript (ES6): duplicate hint,\nimage pre-check, form UX", fill="#ffffff")
    d.box("b3", 800, 80, 300, 60, "Chart.js dashboards\n(fetch /admin/api/stats)", fill="#ffffff")
    d.region(40, 200, 1420, 440, "Application tier — one Flask process (Python 3)")
    d.box("rt", 80, 245, 1340, 70, "Route controllers (blueprints): auth · main (reporter) · staff · admin   —   thin: parse input, call a service, render a template", fill=LIGHT, bold=True)
    d.box("sec", 80, 340, 400, 120, "Cross-cutting security\nFlask-Login sessions · role_required (RBAC)\nCSRF token · security headers (CSP, nosniff)\nlogin lock-out · Werkzeug password hashing", fill="#fff7ed", stroke="#c2410c")
    d.box("svc", 520, 340, 440, 120, "Service layer (services.py)\nworkflow state machine & permissions\nduplicate detection · priority escalation\nstaff suggestion · statistics & reports · audit", fill=LIGHT, bold=True)
    d.box("up", 1000, 340, 420, 120, "Upload handling\nextension + size + magic-byte check\nrandom file names · access-controlled\nroute (not public static files)", fill="#fff7ed", stroke="#c2410c")
    d.box("orm", 80, 500, 1340, 100, "Data access: Flask-SQLAlchemy models — User · MaintenanceRequest · RequestAssignment · RequestUpdate · Feedback · AuditLog\n(CHECK constraints and indexes declared in the model layer)", fill=LIGHT, bold=True)
    d.region(40, 680, 1420, 130, "Data tier — local files (instance/)")
    d.box("db", 120, 720, 560, 70, "SQLite database  campuscare.db\n(swap by DATABASE_URL for PostgreSQL / MySQL)", fill="#ffffff")
    d.box("fs", 760, 720, 560, 70, "uploads/  — validated images, UUID names", fill="#ffffff")
    d.edge("b1", "rt", "HTTP/HTML", "arrow", pts=[(230, 200)] if False else [])
    d.edge("b3", "rt", "JSON", "arrow")
    d.edge("rt", "svc", "", "arrow")
    d.edge("svc", "orm", "", "arrow")
    d.edge("orm", "db", "SQL", "arrow")
    d.edge("up", "fs", "write / read", "arrow", pts=[(1210, 650), (1040, 690)] if False else [])
    d.edge("sec", "rt", "guards every request", "dep")
    save(d, "05_architecture_diagram")


# ============================================================================ 6. STATE
def state():
    d = Diagram("Request workflow (state machine)", 1700, 620)
    S = lambda k, x, y, t, f="#ffffff": d.box(k, x, y, 170, 62, t, fill=f, bold=True, fs=11)
    S("sub", 60, 200, "Submitted"); S("rev", 330, 200, "Under Review", "#fef3c7"); S("asg", 600, 200, "Assigned", "#e0e7ff")
    S("prog", 870, 200, "In Progress", "#dbeafe"); S("res", 1140, 200, "Resolved", "#dcfce7"); S("clo", 1410, 200, "Closed", "#cbd5e1")
    S("rej", 330, 470, "Rejected", "#fee2e2")
    d.label(60, 60, "Roles in [brackets]: A = Administrator, S = assigned Staff, R = reporting Student/Faculty", 11, False, "#475569")
    d.edge("sub", "rev", "[A] start review", "arrow", lbl_off=(0, -14))
    d.edge("rev", "asg", "[A] assign()", "arrow", lbl_off=(0, -14))
    d.edge("asg", "prog", "[S] start work", "arrow", lbl_off=(0, -14))
    d.edge("prog", "res", "[S] resolve + notes", "arrow", lbl_off=(0, -14))
    d.edge("res", "clo", "[R/A] confirm & close", "arrow", lbl_off=(0, -14))
    d.edge("sub", "rej", "[A] reject + reason", "arrow", pts=[(145, 500)], lbl_off=(-30, 20))
    d.edge("rev", "rej", "[A] reject + reason", "arrow", lbl_off=(70, 0))
    d.edge("asg", "rev", "[A] pull back", "arrow", pts=[(685, 130), (415, 130)], lbl_off=(0, -12))
    d.edge("prog", "rev", "[A] pull back", "arrow", pts=[(955, 100), (415, 100)] if False else [(955, 90), (415, 90)], lbl_off=(0, -12))
    d.edge("res", "prog", "[R/A] re-open + reason", "arrow", pts=[(1225, 330), (955, 330)], lbl_off=(0, 14))
    d.note(900, 440, 720, 150, "Rules enforced in services.transition():\n• only the listed (from → to) pairs exist; anything else raises WorkflowError\n• the role AND ownership must match (S = the currently assigned staff member)\n• “Assigned” is reachable only through assign(), so an assignee is always recorded\n• Rejected and Closed are terminal; every change writes history + audit rows", fs=10)
    save(d, "06_workflow_state_diagram")


if __name__ == "__main__":
    use_case(); class_diagram(); sequence(); er(); architecture(); state()
