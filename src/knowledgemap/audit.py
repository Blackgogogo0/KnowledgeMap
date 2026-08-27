import json
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from knowledgemap.db import Database


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    actor: str
    client: str
    event_type: str
    target_id: str
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    created_at: datetime


class AuditLog:
    def __init__(self, db: Database):
        self.db = db

    def append(self, event: AuditEvent) -> AuditEvent:
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, actor, client, event_type, target_id,
                    before_json, after_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.actor,
                    event.client,
                    event.event_type,
                    event.target_id,
                    json.dumps(event.before) if event.before is not None else None,
                    json.dumps(event.after) if event.after is not None else None,
                    event.created_at.isoformat(),
                ),
            )
        return event

    def get(self, event_id: str) -> AuditEvent:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM audit_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return AuditEvent(
            event_id=row["event_id"],
            actor=row["actor"],
            client=row["client"],
            event_type=row["event_type"],
            target_id=row["target_id"],
            before=json.loads(row["before_json"]) if row["before_json"] else None,
            after=json.loads(row["after_json"]) if row["after_json"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
