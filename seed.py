"""Create the database and (optionally) load realistic DEMO data.

    python seed.py            # create tables, add demo data only if the database is empty
    python seed.py --reset    # drop everything and reload the demo data

All names, e-mails and requests are fictional demonstration records.
"""
import sys
from datetime import timedelta

from campuscare import create_app
from campuscare.constants import SLA_HOURS
from campuscare.extensions import db
from campuscare.models import User, utcnow
from campuscare import services as svc

DEMO_PASSWORD = "Demo@1234"

USERS = [  # name, email, role, department, specialty
    ("Dr. Ayesha Malik", "admin@campuscare.test", "admin", "Estate & Maintenance Office", None),
    ("Imran Shah", "electrician@campuscare.test", "staff", "Maintenance", "Electrical"),
    ("Zubair Ahmed", "plumber@campuscare.test", "staff", "Maintenance", "Plumbing & Water"),
    ("Farah Naz", "it.support@campuscare.test", "staff", "IT Services", "IT & Network"),
    ("Kamran Ali", "general@campuscare.test", "staff", "Maintenance", None),
    ("Ali Raza", "student1@campuscare.test", "requester", "Software Engineering", None),
    ("Sana Khan", "student2@campuscare.test", "requester", "Computer Systems", None),
    ("Dr. Nadeem Qureshi", "faculty1@campuscare.test", "requester", "Software Engineering", None),
]

# (requester, hours_ago, title, category, building, location, priority, description, steps, feedback)
# steps: (hours after creation, action, staff-email-or-note)
S = "student1@campuscare.test"; T = "student2@campuscare.test"; F = "faculty1@campuscare.test"
A = "admin@campuscare.test"; EL = "electrician@campuscare.test"; PL = "plumber@campuscare.test"
IT = "it.support@campuscare.test"; GN = "general@campuscare.test"
REQUESTS = [
    (S, 300, "Water cooler out of order", "Plumbing & Water", "Central Library", "Ground floor, near entrance", "Medium",
     "The water cooler on the ground floor of the library has stopped dispensing cold water since Monday.",
     [(1, "review"), (3, "assign", PL), (6, "start"), (30, "resolve", "Replaced faulty thermostat and flushed the supply line."), (40, "close")], (5, "Works perfectly now.")),
    (T, 220, "Network socket dead at desk", "IT & Network", "Computer Lab Complex", "Lab 2, desk 14", "Medium",
     "The wall network socket at desk 14 gives no link light, so the workstation cannot reach the lab server.",
     [(2, "review"), (4, "assign", IT), (8, "start"), (40, "resolve", "Re-terminated the RJ45 jack and tested the patch port."), (50, "close")], (4, "Fixed, but took two days.")),
    (F, 150, "Door lock jammed in Lab 5", "Furniture & Fixtures", "Computer Lab Complex", "Lab 5 main door", "High",
     "The main door of Lab 5 does not lock properly and the key sometimes gets stuck inside the cylinder.",
     [(1, "review"), (2, "assign", GN), (3, "start"), (12, "resolve", "Replaced lock cylinder and issued two new keys to the lab in-charge."), (20, "close")], (3, "Fixed after a follow-up visit.")),
    (T, 160, "Repaint my office wall", "Other", "Administration Block", "Room 5", "Low",
     "Please repaint the wall of Room 5 because the colour has faded over the last two years.",
     [(4, "review"), (6, "reject", "Repainting is covered by the annual maintenance plan and is not handled through service requests.")], None),
    (S, 120, "Ceiling fan making grinding noise", "Electrical", "Main Academic Block", "Room 204", "Medium",
     "The ceiling fan at the back of Room 204 makes a loud grinding noise at medium and high speed.",
     [(1, "review"), (2, "assign", EL), (5, "start"), (30, "resolve", "Replaced worn bearing and tightened the mounting bracket."), (40, "close")], (5, "Quiet again, thank you.")),
    (T, 90, "Water leakage from washroom tap", "Plumbing & Water", "Software Engineering Department", "Ground floor washroom", "High",
     "A tap in the ground floor washroom is leaking continuously and the floor around it is wet.",
     [(1, "review"), (2, "assign", PL), (4, "start"), (20, "resolve", "Replaced the washer and sealed the joint.")], (4, "Good job.")),
    (F, 80, "WiFi dropping in library reading hall", "IT & Network", "Central Library", "Reading hall, 1st floor", "Medium",
     "WiFi disconnects every few minutes in the first floor reading hall, especially in the afternoon.",
     [(2, "review"), (6, "assign", IT)], None),
    (F, 50, "Projector not powering on", "IT & Network", "Computer Lab Complex", "Lab 3", "High",
     "The ceiling projector in Lab 3 shows no sign of power and the remote does nothing. Needed for tomorrow's lecture.",
     [(1, "review"), (3, "assign", IT), (5, "start")], None),
    (S, 14, "Power outage in hostel wing", "Electrical", "Hostel Block", "Block B, 2nd floor corridor", "High",
     "Half of the second floor corridor and four rooms have no electricity since last night.",
     [(1, "review"), (2, "assign", EL), (4, "start")], None),
    (S, 6, "Sparking socket near whiteboard", "Electrical", "Main Academic Block", "Room 112", "Medium",
     "A wall socket near the whiteboard produces sparks when a laptop charger is plugged in.",
     [(0.5, "review"), (1, "assign", EL), (2, "start")], None),
    (F, 20, "Air conditioner not cooling", "HVAC / Cooling", "Software Engineering Department", "Faculty room 3", "High",
     "The split AC in Faculty room 3 runs but only blows warm air.",
     [(1, "review")], None),
    (T, 30, "Broken chairs in seminar room", "Furniture & Fixtures", "Software Engineering Department", "Seminar room", "Low",
     "Three chairs in the seminar room have broken backs and are unsafe to sit on.", [], None),
    (S, 10, "Overflowing dustbins near cafeteria", "Cleaning & Sanitation", "Cafeteria", "Outdoor seating area", "Medium",
     "Dustbins in the outdoor seating area overflow by midday and attract flies.", [], None),
    (T, 4, "Fire extinguisher gauge in red zone", "Safety & Security", "Main Academic Block", "Ground floor corridor", "Medium",
     "The pressure gauge of the fire extinguisher outside Room 101 shows the needle in the red zone.", [], None),
]


def seed_demo():
    users = {}
    for name, email, role, dept, spec in USERS:
        u = svc.create_user(name, email, DEMO_PASSWORD, role, dept, spec)
        users[email] = u
    db.session.commit()
    now = utcnow()

    class F_(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)

    for requester, ago, title, cat, bld, loc, prio, desc, steps, fb in REQUESTS:
        u = users[requester]
        req = svc.create_request(u, F_(title=title, description=desc, category=cat, building=bld, location=loc,
                                       priority=prio), confirm_duplicate=True)
        created = now - timedelta(hours=ago)
        req.created_at = created
        req.due_at = created + timedelta(hours=SLA_HOURS[req.priority])
        for up in req.updates:
            up.created_at = created
        for h, action, *arg in steps:
            at = created + timedelta(hours=h)
            if action == "review":
                svc.transition(req, users[A], "Under Review")
            elif action == "assign":
                svc.assign(req, users[A], users[arg[0]].id, "Please attend as soon as possible." if req.priority in ("High", "Critical") else None)
                req.assignments[-1].assigned_at = at
            elif action == "start":
                svc.transition(req, req.assigned_staff, "In Progress")
            elif action == "resolve":
                svc.transition(req, req.assigned_staff, "Resolved", arg[0])
                req.resolved_at = at
            elif action == "close":
                svc.transition(req, u, "Closed")
                req.closed_at = at
            elif action == "reject":
                svc.transition(req, users[A], "Rejected", arg[0])
            req.updates[-1].created_at = at
        if fb:
            svc.submit_feedback(req, u, fb[0], fb[1])
            req.feedback.created_at = (req.closed_at or req.resolved_at or now)
        req.updated_at = req.updates[-1].created_at
    # A deliberate near-duplicate to demonstrate duplicate flagging
    dup = svc.create_request(users[F], F_(title="Projector flickers intermittently", description="Projector in Lab 3 flickers and then turns off after a few minutes.",
                                          category="IT & Network", building="Computer Lab Complex", location="Lab 3", priority="Medium"),
                             confirm_duplicate=True)
    db.session.commit()
    return users


def main():
    app = create_app()
    with app.app_context():
        if "--reset" in sys.argv:
            db.drop_all()
        db.create_all()
        if User.query.count() == 0:
            seed_demo()
            print(f"Demo data loaded. All demo accounts use password: {DEMO_PASSWORD}")
        else:
            print("Database already contains data; nothing seeded (use --reset to rebuild).")


if __name__ == "__main__":
    main()
