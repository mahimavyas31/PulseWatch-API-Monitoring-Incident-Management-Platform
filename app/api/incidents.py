from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Incident, Monitor, User
from app.schemas import IncidentOut
from app.security import current_user

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
def list_incidents(status: Literal["open", "resolved"] | None = None,
                   monitor_id: int | None = None,
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = (select(Incident).join(Monitor, Monitor.id == Incident.monitor_id)
         .where(Monitor.user_id == user.id))  # ownership enforced in the query
    if status:
        q = q.where(Incident.status == status)
    if monitor_id is not None:
        q = q.where(Incident.monitor_id == monitor_id)
    return db.scalars(q.order_by(Incident.id.desc()).limit(limit).offset(offset)).all()
