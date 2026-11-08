# Database design

Six tables, third normal form. Types are SQLAlchemy/SQLite types; CHECK constraints are enforced by SQLite.

| Table | Purpose | Key constraints / indexes |
|---|---|---|
| `users` | All accounts (role column) | PK id; UNIQUE email; CHECK role IN (requester, staff, admin); index on role |
| `maintenance_requests` | One row per reported problem | PK id; UNIQUE reference_id; FK requester_id → users; FK duplicate_of_id → self; CHECK status/priority/requested_priority; indexes (status, priority) and (building, category, status) for duplicate lookup |
| `request_assignments` | Assignment history; the active row is the current assignee | PK id; FK request_id, staff_id, assigned_by_id; index on request_id, staff_id |
| `request_updates` | Immutable history of status, assignment and priority events | PK id; FK request_id, author_id |
| `feedback` | Rating (1–5) and comment after resolution | PK id; UNIQUE request_id (one per request); CHECK rating BETWEEN 1 AND 5 |
| `audit_logs` | Security and workflow audit trail | PK id; FK user_id (nullable); indexes on action, created_at, (entity_type, entity_id) |

Design decisions: assignments, history and feedback are separate tables so re-assignment, re-opening and priority changes
never overwrite earlier facts; `requested_priority` is stored next to the effective `priority` so automatic escalation stays visible.
See `docs/uml/04_er_diagram.png`.
