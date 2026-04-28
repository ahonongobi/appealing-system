from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class UserOut(BaseModel):
    id: int
    name: str
    role: str
    class Config:
        from_attributes = True

class CaseCreate(BaseModel):
    title: str
    description: str

class CaseOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    created_by: int
    assigned_to: Optional[int]
    created_at: datetime
    deadline: Optional[datetime]
    class Config:
        from_attributes = True

class DecisionOut(BaseModel):
    id: int
    case_id: int
    actor_role: str
    decision: str
    justification: str
    timestamp: datetime
    class Config:
        from_attributes = True

class AppealOut(BaseModel):
    id: int
    case_id: int
    reason: str
    timestamp: datetime
    class Config:
        from_attributes = True

class AuditLogOut(BaseModel):
    id: int
    case_id: int
    actor: str
    action: str
    timestamp: datetime
    class Config:
        from_attributes = True

class CaseDetail(BaseModel):
    id: int
    title: str
    description: str
    status: str
    created_by: int
    assigned_to: Optional[int]
    created_at: datetime
    deadline: Optional[datetime]
    decisions: List[DecisionOut]
    appeals: List[AppealOut]
    audit_logs: List[AuditLogOut]
    creator: Optional[UserOut]
    assignee: Optional[UserOut]
    class Config:
        from_attributes = True

class DecisionCreate(BaseModel):
    case_id: int
    decision: str  # approve | reject
    justification: str

class AppealCreate(BaseModel):
    case_id: int
    reason: str
