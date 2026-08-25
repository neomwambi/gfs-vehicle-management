"""Audit trail helper - every meaningful state change must call this."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import AuditLog


def _serialize(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def write_audit(
    db: Session,
    *,
    table_name: str,
    record_id: int,
    action: str,
    changed_by: int | None,
    old_value: Any = None,
    new_value: Any = None,
) -> AuditLog:
    entry = AuditLog(
        TableName=table_name,
        RecordID=record_id,
        Action=action,
        ChangedBy=changed_by,
        ChangedAt=datetime.utcnow(),
        OldValue=_serialize(old_value),
        NewValue=_serialize(new_value),
    )
    db.add(entry)
    return entry
