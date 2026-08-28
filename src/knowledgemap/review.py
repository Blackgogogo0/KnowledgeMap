import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.models import ClaimRecord, ClaimStatus, ReviewAction


class ReviewService:
    def __init__(
        self,
        db: Database,
        audit: AuditLog,
        clock: Callable[[], datetime] | None = None,
    ):
        self.db = db
        self.audit = audit
        self.clock = clock or (lambda: datetime.now(UTC))

    def list(self, status: ClaimStatus = ClaimStatus.PENDING) -> list[ClaimRecord]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM claims WHERE review_status = ? ORDER BY created_at, claim_id",
                (status.value,),
            ).fetchall()
        return [self._record(row) for row in rows]

    def decide(
        self,
        claim_id: str,
        action: ReviewAction,
        actor: str,
        client: str,
        note: str | None = None,
    ) -> ClaimRecord:
        now = self.clock()
        with self.db.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
            if row is None:
                raise KnowledgeMapError("CLAIM_NOT_FOUND", "Claim was not found.")
            before = row["review_status"]
            if action == ReviewAction.RESEARCH_MORE:
                connection.execute(
                    """
                    INSERT INTO review_items (
                        review_item_id, target_type, target_id, proposed_action,
                        note, status, created_at
                    ) VALUES (?, 'claim', ?, 'research-more', ?, 'pending', ?)
                    """,
                    (str(uuid4()), claim_id, note, now.isoformat()),
                )
                after = before
            else:
                after = {
                    ReviewAction.ACCEPT: ClaimStatus.ACCEPTED.value,
                    ReviewAction.REJECT: ClaimStatus.REJECTED.value,
                    ReviewAction.DOWNGRADE_TO_DISPUTED: ClaimStatus.DISPUTED.value,
                }[action]
                connection.execute(
                    """
                    UPDATE claims SET review_status = ?, reviewed_at = ?, reviewed_by = ?
                    WHERE claim_id = ?
                    """,
                    (after, now.isoformat(), actor, claim_id),
                )
                connection.execute("DELETE FROM claims_fts WHERE claim_id = ?", (claim_id,))
                if after == ClaimStatus.ACCEPTED.value:
                    projection = connection.execute(
                        """
                        SELECT c.statement,
                               COALESCE(group_concat(DISTINCT kv.title), '') AS title,
                               COALESCE(group_concat(DISTINCT kv.tags_json), '') AS tags,
                               COALESCE(group_concat(DISTINCT kv.aliases_json), '') AS aliases
                        FROM claims c
                        LEFT JOIN knowledge_view_claims kvc ON kvc.claim_id = c.claim_id
                        LEFT JOIN knowledge_views kv ON kv.knowledge_view_id = kvc.knowledge_view_id
                        WHERE c.claim_id = ? GROUP BY c.claim_id
                        """,
                        (claim_id,),
                    ).fetchone()
                    connection.execute(
                        """
                        INSERT INTO claims_fts (claim_id, statement, title, tags, aliases)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            claim_id,
                            projection["statement"],
                            projection["title"],
                            projection["tags"],
                            projection["aliases"],
                        ),
                    )
                    originals = connection.execute(
                        """
                        SELECT to_claim_id FROM claim_relations
                        WHERE from_claim_id = ? AND relation = 'supersedes'
                        """,
                        (claim_id,),
                    ).fetchall()
                    for original in originals:
                        connection.execute(
                            "UPDATE claims SET review_status = 'superseded' WHERE claim_id = ?",
                            (original["to_claim_id"],),
                        )
                        connection.execute(
                            "DELETE FROM claims_fts WHERE claim_id = ?",
                            (original["to_claim_id"],),
                        )
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, actor, client, event_type, target_id,
                    before_json, after_json, created_at
                ) VALUES (?, ?, ?, 'claim.reviewed', ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    actor,
                    client,
                    claim_id,
                    json.dumps({"review_status": before}),
                    json.dumps({"review_status": after, "action": action.value, "note": note}),
                    now.isoformat(),
                ),
            )
            updated = connection.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        return self._record(updated)

    @staticmethod
    def _record(row) -> ClaimRecord:
        return ClaimRecord(
            claim_id=row["claim_id"],
            statement=row["statement"],
            review_status=ClaimStatus(row["review_status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
