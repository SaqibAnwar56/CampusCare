# CampusCare — Smart Campus Service and Maintenance Management System

SW315 Software Construction and Development · Lab 16 (Complex Engineering Problem) · MUET Jamshoro

CampusCare is a Flask web application where students/faculty report campus maintenance problems,
maintenance staff resolve assigned tasks, and administrators triage, assign, monitor and report.

**Repository URL:** `<https://github.com/SaqibAnwar56/CampusCare?utm_source=chatgpt.com>`

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py --reset             # creates instance/campuscare.db with DEMO data
python app.py                      # open http://127.0.0.1:5000
```

All demo accounts use the password **`Demo@1234`** (demo data only — never reuse it).

| Role | Email |
|---|---|
| Administrator | admin@campuscare.test |
| Maintenance staff | electrician@campuscare.test, plumber@campuscare.test, it.support@campuscare.test, general@campuscare.test |
| Student / Faculty | student1@campuscare.test, student2@campuscare.test, faculty1@campuscare.test |

Run `python seed.py` (without `--reset`) to create an empty database. Self-registration always creates a Student/Faculty account.

## Tests

```bash
python -m pytest -v          # 37 automated tests; writes test-results/results.json
```

## Project layout

```
app.py, config.py, seed.py     entry point, configuration, demo data
campuscare/
  models.py                    SQLAlchemy models (User, MaintenanceRequest, RequestAssignment, RequestUpdate, Feedback, AuditLog)
  services.py                  business rules: workflow, permissions, duplicates, escalation, reports
  routes/                      thin blueprints: auth, main (reporter), staff, admin
  templates/, static/          Jinja2 + Bootstrap 5 UI, Chart.js (vendored, works offline)
tests/                         pytest suite
tools/make_uml.py              regenerates docs/uml/*.png and *.drawio
docs/                          UML (PNG + editable Draw.io), DATABASE.md, DEVOPS.md, screenshots
.github/workflows/ci.yml       GitHub Actions: install, compile, test
```

## Key behaviours

* Workflow `Submitted → Under Review → Assigned → In Progress → Resolved → Closed` (+ `Rejected`), enforced by one transition table with role and ownership checks.
* Duplicate detection (same building + category + similar location among open requests), with a live hint and a server-side confirmation step.
* Safety escalation: category *Safety & Security* is at least High; danger keywords (e.g. "sparking", "smoke") force Critical. The reporter's original choice is kept.
* Target resolution times by priority (Critical 8 h, High 24 h, Medium 72 h, Low 168 h) drive overdue detection.
* Workload-aware assignment suggestions (specialty match, then fewest open tasks).
* Privacy: staff see the reporter's first name only; contact e-mail is visible to administrators.
* Security: password hashing, lock-out after 5 failed logins, CSRF tokens, CSP/nosniff headers, upload checks (extension, size, magic bytes, random names, access-controlled download), audit log.

## Production notes

Set `SECRET_KEY` and `DATABASE_URL` (see `.env.example`), run behind a WSGI server (e.g. `gunicorn app:app`) with HTTPS.
