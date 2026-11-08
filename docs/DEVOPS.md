# Version control and DevOps

## Create the repository (the group must do this — no repository exists yet)

```bash
git init
git branch -M main
git add .
git commit -m "chore: project scaffold, configuration and requirements"
git remote add origin <YOUR-REPOSITORY-URL>
git push -u origin main
```

## Suggested commit plan (one or two commits per member, made by the member who did the work)

1. `docs: requirements, stakeholders and constraints (SRS draft)`
2. `feat(db): SQLAlchemy models, constraints and indexes`
3. `feat(auth): registration, login, lock-out, RBAC decorator`
4. `feat(workflow): transition table and request service`
5. `feat(requests): submission form, duplicate detection, image validation`
6. `feat(staff): task dashboard and history`
7. `feat(admin): dashboard, assignment, priority, users, reports, audit`
8. `feat(ui): base layout, CSS, charts`
9. `test: pytest suite for auth, workflow, uploads, reports`
10. `ci: GitHub Actions workflow`
11. `docs: UML diagrams, database notes, report`

Use feature branches and pull requests where possible; keep the real commit history as evidence.

## CI pipeline (`.github/workflows/ci.yml`)

On every push / pull request: checkout → set up Python 3.10 and 3.12 → `pip install -r requirements.txt` →
`python -m compileall` (build check) → `pytest -v` → upload `test-results/results.json`.
After pushing, take a screenshot of the green Actions run as evidence.

## Deployment considerations

Gunicorn behind Nginx with HTTPS; environment variables for `SECRET_KEY`/`DATABASE_URL`; PostgreSQL instead of SQLite
for concurrent use; uploads on persistent storage; scheduled database backups.
