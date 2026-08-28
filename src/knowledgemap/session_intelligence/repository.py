import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.session_intelligence.models import (
    KnowledgeNeedStatus,
    SessionInsightSubmission,
    TaskStateSnapshot,
)
from knowledgemap.session_intelligence.needs import canonicalize_question, rank_need


@dataclass(frozen=True)
class AnalysisRecord:
    checkpoint_id: str
    client: str
    session_id: str
    created_at: datetime
    idempotent_replay: bool = False


class SessionIntelligenceRepository:
    def __init__(self, db: Database, clock: Callable[[], datetime] | None = None):
        self.db = db
        self.clock = clock or (lambda: datetime.now(UTC))

    def commit_submission(
        self,
        submission: SessionInsightSubmission,
        snapshots: list[TaskStateSnapshot],
        provider_mode: str = "client_assisted",
    ) -> AnalysisRecord:
        created_at = self.clock()
        with self.db.transaction() as connection:
            existing = connection.execute(
                """
                SELECT client, session_id, content_hash, created_at
                FROM session_checkpoints WHERE checkpoint_id = ?
                """,
                (submission.checkpoint_id,),
            ).fetchone()
            if existing:
                if (
                    existing["client"] == submission.client
                    and existing["session_id"] == submission.session_id
                    and existing["content_hash"] == submission.content_hash
                ):
                    return AnalysisRecord(
                        submission.checkpoint_id,
                        submission.client,
                        submission.session_id,
                        datetime.fromisoformat(existing["created_at"]),
                        True,
                    )
                raise KnowledgeMapError(
                    "CHECKPOINT_CONFLICT", "Checkpoint ID already represents other content."
                )

            active = connection.execute(
                """
                SELECT checkpoint_id FROM session_checkpoints
                WHERE client = ? AND session_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (submission.client, submission.session_id),
            ).fetchone()
            active_id = active["checkpoint_id"] if active else None
            if submission.previous_checkpoint_id != active_id:
                raise KnowledgeMapError(
                    "CHECKPOINT_CONFLICT",
                    "Submission does not continue the active checkpoint.",
                    {"expected": active_id},
                )
            if active_id:
                connection.execute(
                    "UPDATE session_checkpoints SET is_active = 0 WHERE checkpoint_id = ?",
                    (active_id,),
                )
            connection.execute(
                """
                INSERT INTO session_checkpoints (
                    checkpoint_id, client, session_id, previous_checkpoint_id,
                    content_hash, provider_mode, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    submission.checkpoint_id,
                    submission.client,
                    submission.session_id,
                    submission.previous_checkpoint_id,
                    submission.content_hash,
                    provider_mode,
                    created_at.isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO task_episodes VALUES (?, ?, ?, ?)",
                [
                    (
                        snapshot.episode_id,
                        submission.checkpoint_id,
                        snapshot.model_dump_json(),
                        created_at.isoformat(),
                    )
                    for snapshot in snapshots
                ],
            )
            for delta in submission.episode_deltas:
                connection.execute(
                    """
                    INSERT INTO task_state_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        submission.checkpoint_id,
                        delta.episode_id,
                        delta.field.value,
                        delta.operation,
                        delta.value,
                        delta.previous_value,
                        json.dumps([e.model_dump() for e in delta.evidence]),
                    ),
                )
            for route in submission.routes:
                connection.execute(
                    "INSERT INTO gap_routes VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid4()),
                        submission.checkpoint_id,
                        route.unresolved_item_id,
                        route.route.value,
                        route.rationale,
                        json.dumps([e.model_dump() for e in route.evidence]),
                    ),
                )
            for need in submission.knowledge_needs:
                connection.execute(
                    """
                    INSERT INTO knowledge_needs VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        need.need_id,
                        submission.checkpoint_id,
                        need.unresolved_item_id,
                        need.question,
                        canonicalize_question(need.question),
                        need.decision_it_changes,
                        need.current_assumption,
                        need.knowledge_type.value,
                        json.dumps(need.preferred_source_types),
                        need.version_or_time_scope,
                        need.why_context_is_insufficient,
                        need.confidence,
                        rank_need(need),
                        KnowledgeNeedStatus.OPEN.value,
                        created_at.isoformat(),
                    ),
                )
                connection.executemany(
                    "INSERT INTO knowledge_need_evidence VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            need.need_id,
                            submission.client,
                            submission.session_id,
                            evidence.message_id,
                            evidence.excerpt,
                        )
                        for evidence in need.evidence
                    ],
                )
        return AnalysisRecord(
            submission.checkpoint_id,
            submission.client,
            submission.session_id,
            created_at,
        )

    def get_latest_state(
        self, client: str, session_id: str
    ) -> tuple[AnalysisRecord, list[TaskStateSnapshot]] | None:
        with self.db.connect() as connection:
            checkpoint = connection.execute(
                """
                SELECT * FROM session_checkpoints
                WHERE client = ? AND session_id = ? AND is_active = 1 LIMIT 1
                """,
                (client, session_id),
            ).fetchone()
            if not checkpoint:
                return None
            states = connection.execute(
                "SELECT state_json FROM task_episodes WHERE checkpoint_id = ?",
                (checkpoint["checkpoint_id"],),
            ).fetchall()
        return (
            AnalysisRecord(
                checkpoint["checkpoint_id"],
                client,
                session_id,
                datetime.fromisoformat(checkpoint["created_at"]),
            ),
            [TaskStateSnapshot.model_validate_json(row["state_json"]) for row in states],
        )

    def list_needs(
        self, status: str | None = None, session_id: str | None = None, top_k: int = 50
    ) -> list[dict]:
        clauses: list[str] = []
        values: list[object] = []
        if status:
            clauses.append("n.status = ?")
            values.append(status)
        if session_id:
            clauses.append("c.session_id = ?")
            values.append(session_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(top_k)
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT n.*, c.client, c.session_id FROM knowledge_needs n
                JOIN session_checkpoints c ON c.checkpoint_id = n.checkpoint_id
                """ + where + " ORDER BY n.rank_score DESC LIMIT ?",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def set_need_status(self, need_id: str, status: KnowledgeNeedStatus) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE knowledge_needs SET status = ? WHERE knowledge_need_id = ?",
                (status.value, need_id),
            )

    def attach_resolution(self, need_id: str, claim_ids: list[str]) -> None:
        with self.db.transaction() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO knowledge_need_claims VALUES (?, ?, ?)",
                [(need_id, claim_id, self.clock().isoformat()) for claim_id in claim_ids],
            )

    def record_feedback(self, need_id: str, feedback: str) -> None:
        if feedback not in {"useful", "not_useful", "resolved"}:
            raise KnowledgeMapError("INVALID_FEEDBACK", "Unsupported feedback value.")
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO knowledge_need_feedback VALUES (?, ?, ?, ?)",
                (str(uuid4()), need_id, feedback, self.clock().isoformat()),
            )

