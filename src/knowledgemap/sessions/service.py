from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from knowledgemap.audit import AuditEvent, AuditLog
from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sessions.base import SessionMessage, SessionMetadata, SessionReader


class SessionGrant(BaseModel):
    grant_id: str
    client: str
    session_id: str
    granted_at: datetime
    content_hash: str
    revoked_at: datetime | None = None


class AuthorizedSession(BaseModel):
    grant: SessionGrant
    messages: list[SessionMessage]


class SessionService:
    def __init__(
        self,
        db: Database,
        audit: AuditLog,
        readers: dict[str, SessionReader],
    ):
        self.db = db
        self.audit = audit
        self.readers = readers

    def list(
        self, client: str, project: str | None = None, since: datetime | None = None
    ) -> list[SessionMetadata]:
        return self._reader(client).list_metadata(project, since)

    def grant_and_read(
        self,
        client: str,
        session_id: str,
        confirm_read: bool,
        now: datetime,
    ) -> AuthorizedSession:
        if not confirm_read:
            raise KnowledgeMapError(
                "SESSION_CONFIRMATION_REQUIRED",
                "Session body access requires explicit confirmation.",
            )
        reader = self._reader(client)
        raw = reader.read_raw(session_id)
        grant = SessionGrant(
            grant_id=str(uuid4()),
            client=client,
            session_id=session_id,
            granted_at=now,
            content_hash=sha256(raw).hexdigest(),
        )
        with self.db.transaction() as connection:
            connection.execute(
                """
                UPDATE session_grants SET revoked_at = ?
                WHERE client = ? AND session_id = ? AND revoked_at IS NULL
                """,
                (now.isoformat(), client, session_id),
            )
            connection.execute(
                """
                INSERT INTO session_grants (
                    grant_id, client, session_id, granted_at, content_hash
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    grant.grant_id,
                    client,
                    session_id,
                    now.isoformat(),
                    grant.content_hash,
                ),
            )
        self.audit.append(
            AuditEvent(
                actor="user",
                client=client,
                event_type="session.granted",
                target_id=session_id,
                after={"grant_id": grant.grant_id, "content_hash": grant.content_hash},
                created_at=now,
            )
        )
        return AuthorizedSession(grant=grant, messages=reader.read_messages(session_id))

    def read(self, client: str, session_id: str) -> AuthorizedSession:
        grant = self._active_grant(client, session_id)
        reader = self._reader(client)
        raw = reader.read_raw(session_id)
        if sha256(raw).hexdigest() != grant.content_hash:
            raise KnowledgeMapError(
                "SESSION_CHANGED",
                "Session content changed after authorization; create a new grant.",
            )
        return AuthorizedSession(grant=grant, messages=reader.read_messages(session_id))

    def revoke(self, client: str, session_id: str, now: datetime) -> SessionGrant:
        grant = self._active_grant(client, session_id)
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE session_grants SET revoked_at = ? WHERE grant_id = ?",
                (now.isoformat(), grant.grant_id),
            )
        revoked = grant.model_copy(update={"revoked_at": now})
        self.audit.append(
            AuditEvent(
                actor="user",
                client=client,
                event_type="session.revoked",
                target_id=session_id,
                before={"grant_id": grant.grant_id, "revoked_at": None},
                after={"grant_id": grant.grant_id, "revoked_at": now.isoformat()},
                created_at=now,
            )
        )
        return revoked

    def _active_grant(self, client: str, session_id: str) -> SessionGrant:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM session_grants
                WHERE client = ? AND session_id = ? AND revoked_at IS NULL
                ORDER BY granted_at DESC LIMIT 1
                """,
                (client, session_id),
            ).fetchone()
        if row is None:
            raise KnowledgeMapError(
                "SESSION_NOT_AUTHORIZED", "Session has no active authorization grant."
            )
        return SessionGrant(
            grant_id=row["grant_id"],
            client=row["client"],
            session_id=row["session_id"],
            granted_at=datetime.fromisoformat(row["granted_at"]),
            content_hash=row["content_hash"],
            revoked_at=None,
        )

    def _reader(self, client: str) -> SessionReader:
        try:
            return self.readers[client]
        except KeyError as error:
            raise KnowledgeMapError(
                "UNSUPPORTED_SESSION_CLIENT", f"Unsupported session client: {client}"
            ) from error
