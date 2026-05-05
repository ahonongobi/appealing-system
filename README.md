# General Appeal System

A governance-controlled, multi-actor workflow system enforcing strict separation of roles, immutable decisions, automatic routing, and audit logging.

## Project Structure

```
appeal_system/
├── backend/
│   ├── main.py          # FastAPI application + all endpoints
│   ├── models.py        # SQLAlchemy ORM models
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── crud.py          # Business logic helpers
│   ├── database.py      # SQLite database setup
│   └── requirements.txt
└── frontend/
    ├── templates/
    │   ├── index.html      # Portal / role selector
    │   ├── requestor.html  # Requestor UI
    │   ├── authority.html  # Authority UI
    │   └── reviewer.html   # Reviewer UI
    └── static/
        └── css/
            └── shared.css
```



## Workflow

```
[Requestor] SUBMIT CASE
    ↓ auto-assigned
[Authority] UNDER_REVIEW → DECIDED (approve/reject)
    ↓
[Requestor] sees decision → ACCEPT (closes) or APPEAL
    ↓ appeal filed
[SYSTEM] auto-routes to Reviewer — Authority BYPASSED
    ↓
[Reviewer] APPEALED → FINALIZED (final, immutable)
```

### Auto-escalation
If Authority misses the 7-day deadline, the system auto-escalates to ESCALATED status and routes the case to the Reviewer.

---

## Governance Enforcements

| Rule | Enforcement |
|------|-------------|
| Authority cannot review appeals | Status check at API + UI filter |
| Reviewer not in initial decisions | Role guard on `/decisions` |
| Justification mandatory | Min 20 chars, enforced in backend |
| Decisions immutable | No PATCH/PUT endpoints exist |
| Auto-routing on appeal | Status machine in backend, no manual routing |
| Deadline enforcement | Auto-escalation on every `/cases` fetch |
| Audit trail | Append-only `audit_logs` table |
| Conflict of interest | Authority blocked from APPEALED cases |

---

## API Endpoints

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | /cases | Requestor | Submit new case |
| GET | /cases | All | List cases (filtered by role) |
| GET | /cases/{id} | All | Get case detail |
| POST | /decisions | Authority/Reviewer | Submit decision |
| POST | /appeals | Requestor | File appeal |
| POST | /cases/{id}/accept | Requestor | Accept decision |
| GET | /audit/{id} | All | Get audit log |
| GET | /users | All | List users |






