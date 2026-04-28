from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import models, schemas, crud
from database import engine, get_db
import os

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="General Appeal System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")

# Seed demo users on startup
@app.on_event("startup")
def seed_users():
    from database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            users = [
                models.User(id=1, name="Alice Requestor", role="requestor"),
                models.User(id=2, name="Bob Authority", role="authority"),
                models.User(id=3, name="Carol Reviewer", role="reviewer"),
            ]
            db.add_all(users)
            db.commit()
    finally:
        db.close()

def get_current_user(x_user_id: int = Header(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == x_user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user

def require_role(role: str):
    def checker(user: models.User = Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(status_code=403, detail=f"Only {role} can perform this action")
        return user
    return checker

# ─── FRONTEND ROUTES ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    with open("../frontend/templates/index.html") as f:
        return f.read()

@app.get("/requestor", response_class=HTMLResponse)
def requestor_ui():
    with open("../frontend/templates/requestor.html") as f:
        return f.read()

@app.get("/authority", response_class=HTMLResponse)
def authority_ui():
    with open("../frontend/templates/authority.html") as f:
        return f.read()

@app.get("/reviewer", response_class=HTMLResponse)
def reviewer_ui():
    with open("../frontend/templates/reviewer.html") as f:
        return f.read()

# ─── USER API ─────────────────────────────────────────────────────────────────

@app.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()

# ─── CASES API ────────────────────────────────────────────────────────────────

@app.post("/cases", response_model=schemas.CaseOut)
def create_case(payload: schemas.CaseCreate, user=Depends(require_role("requestor")), db: Session = Depends(get_db)):
    # Find an authority user to assign to
    authority = db.query(models.User).filter(models.User.role == "authority").first()
    if not authority:
        raise HTTPException(status_code=500, detail="No authority user found")

    case = models.Case(
        title=payload.title,
        description=payload.description,
        status="SUBMITTED",
        created_by=user.id,
        assigned_to=authority.id,
        deadline=datetime.utcnow() + timedelta(days=7)
    )
    db.add(case)
    db.flush()

    # Auto-assign → UNDER_REVIEW
    case.status = "UNDER_REVIEW"
    crud.log_action(db, case.id, user.name, "CASE_SUBMITTED")
    crud.log_action(db, case.id, "SYSTEM", f"AUTO_ASSIGNED_TO:{authority.name}")
    db.commit()
    db.refresh(case)
    return case

@app.get("/cases", response_model=list[schemas.CaseOut])
def list_cases(user=Depends(get_current_user), db: Session = Depends(get_db)):
    # Auto-escalate overdue cases before returning
    crud.auto_escalate_overdue(db)

    if user.role == "requestor":
        return db.query(models.Case).filter(models.Case.created_by == user.id).all()
    elif user.role == "authority":
        return db.query(models.Case).filter(
            models.Case.assigned_to == user.id,
            models.Case.status.in_(["UNDER_REVIEW"])
        ).all()
    elif user.role == "reviewer":
        return db.query(models.Case).filter(
            models.Case.status.in_(["APPEALED", "FINALIZED", "ESCALATED"])
        ).all()
    return []

@app.get("/cases/{case_id}", response_model=schemas.CaseDetail)
def get_case(case_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Access control
    if user.role == "requestor" and case.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your case")
    if user.role == "authority" and case.status == "APPEALED":
        raise HTTPException(status_code=403, detail="Authority cannot access appeal stage — governance enforced")

    decisions = db.query(models.Decision).filter(models.Decision.case_id == case_id).all()
    appeals = db.query(models.Appeal).filter(models.Appeal.case_id == case_id).all()
    logs = db.query(models.AuditLog).filter(models.AuditLog.case_id == case_id).all()

    return schemas.CaseDetail(
        **{c.name: getattr(case, c.name) for c in case.__table__.columns},
        decisions=decisions,
        appeals=appeals,
        audit_logs=logs,
        creator=case.creator,
        assignee=case.assignee
    )

# ─── DECISIONS API ────────────────────────────────────────────────────────────

@app.post("/decisions", response_model=schemas.DecisionOut)
def submit_decision(payload: schemas.DecisionCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.query(models.Case).filter(models.Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not payload.justification or len(payload.justification.strip()) < 20:
        raise HTTPException(status_code=422, detail="Justification must be at least 20 characters")

    # Authority decision
    if user.role == "authority":
        if case.status != "UNDER_REVIEW":
            raise HTTPException(status_code=400, detail=f"Cannot decide case in status: {case.status}")
        if case.assigned_to != user.id:
            raise HTTPException(status_code=403, detail="Not assigned to you")

        decision = models.Decision(
            case_id=case.id,
            actor_role="authority",
            actor_id=user.id,
            decision=payload.decision,
            justification=payload.justification
        )
        db.add(decision)
        case.status = "DECIDED"
        crud.log_action(db, case.id, user.name, f"AUTHORITY_DECIDED:{payload.decision.upper()}")
        db.commit()
        db.refresh(decision)
        return decision

    # Reviewer final decision
    elif user.role == "reviewer":
        if case.status not in ("APPEALED", "ESCALATED"):
            raise HTTPException(status_code=400, detail=f"Cannot finalize case in status: {case.status}")

        decision = models.Decision(
            case_id=case.id,
            actor_role="reviewer",
            actor_id=user.id,
            decision=payload.decision,
            justification=payload.justification
        )
        db.add(decision)
        case.status = "FINALIZED"
        crud.log_action(db, case.id, user.name, f"REVIEWER_FINALIZED:{payload.decision.upper()}")
        db.commit()
        db.refresh(decision)
        return decision

    else:
        raise HTTPException(status_code=403, detail="Requestors cannot submit decisions")

# ─── APPEALS API ──────────────────────────────────────────────────────────────

@app.post("/appeals", response_model=schemas.AppealOut)
def submit_appeal(payload: schemas.AppealCreate, user=Depends(require_role("requestor")), db: Session = Depends(get_db)):
    case = db.query(models.Case).filter(models.Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your case")
    if case.status != "DECIDED":
        raise HTTPException(status_code=400, detail="Can only appeal after Authority decision")

    if not payload.reason or len(payload.reason.strip()) < 10:
        raise HTTPException(status_code=422, detail="Appeal reason must be at least 10 characters")

    appeal = models.Appeal(case_id=case.id, reason=payload.reason)
    db.add(appeal)

    # CRITICAL: route directly to Reviewer — Authority completely bypassed
    case.status = "APPEALED"
    crud.log_action(db, case.id, user.name, "APPEAL_SUBMITTED")
    crud.log_action(db, case.id, "SYSTEM", "AUTO_ROUTED_TO_REVIEWER:Authority_bypassed")
    db.commit()
    db.refresh(appeal)
    return appeal

@app.post("/cases/{case_id}/accept")
def accept_decision(case_id: int, user=Depends(require_role("requestor")), db: Session = Depends(get_db)):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your case")
    if case.status != "DECIDED":
        raise HTTPException(status_code=400, detail="Nothing to accept")

    case.status = "FINALIZED"
    crud.log_action(db, case.id, user.name, "REQUESTOR_ACCEPTED_DECISION")
    db.commit()
    return {"status": "FINALIZED", "message": "Decision accepted. Case closed."}

# ─── AUDIT API ────────────────────────────────────────────────────────────────

@app.get("/audit/{case_id}", response_model=list[schemas.AuditLogOut])
def get_audit(case_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.AuditLog).filter(models.AuditLog.case_id == case_id).order_by(models.AuditLog.timestamp).all()
