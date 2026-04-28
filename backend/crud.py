from sqlalchemy.orm import Session
from datetime import datetime
import models

def log_action(db: Session, case_id: int, actor: str, action: str):
    log = models.AuditLog(case_id=case_id, actor=actor, action=action)
    db.add(log)

def auto_escalate_overdue(db: Session):
    """Auto-escalate cases where Authority missed the deadline."""
    overdue = db.query(models.Case).filter(
        models.Case.status == "UNDER_REVIEW",
        models.Case.deadline < datetime.utcnow()
    ).all()
    for case in overdue:
        case.status = "ESCALATED"
        log_action(db, case.id, "SYSTEM", "AUTO_ESCALATED:Deadline_exceeded_routed_to_Reviewer")
    if overdue:
        db.commit()
