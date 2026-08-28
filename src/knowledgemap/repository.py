import json
from datetime import datetime
from uuid import uuid4

from knowledgemap.db import Database
from knowledgemap.models import ClaimRecord, ClaimStatus, EvidenceRecord, SourceRecord


def _id() -> str:
    return str(uuid4())


class SourceRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self, source_type: str, canonical_uri: str, created_at: datetime
    ) -> SourceRecord:
        record = SourceRecord(
            source_id=_id(),
            type=source_type,
            canonical_uri=canonical_uri,
            created_at=created_at,
        )
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO sources (source_id, type, canonical_uri, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    record.source_id,
                    record.type,
                    record.canonical_uri,
                    record.created_at.isoformat(),
                ),
            )
        return record

    def get_or_create(
        self, source_type: str, canonical_uri: str, created_at: datetime
    ) -> tuple[SourceRecord, bool]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE canonical_uri = ?", (canonical_uri,)
            ).fetchone()
        if row is not None:
            return SourceRecord(
                source_id=row["source_id"],
                type=row["type"],
                canonical_uri=row["canonical_uri"],
                created_at=datetime.fromisoformat(row["created_at"]),
            ), False
        return self.create(source_type, canonical_uri, created_at), True


class EvidenceRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        source_id: str,
        version: str,
        content_hash: str,
        retrieved_at: datetime,
        local_blob_path: str,
        media_type: str,
        locator: dict[str, object],
    ) -> EvidenceRecord:
        record = EvidenceRecord(
            evidence_id=_id(),
            source_id=source_id,
            version=version,
            content_hash=content_hash,
            retrieved_at=retrieved_at,
            local_blob_path=local_blob_path,
            media_type=media_type,
            locator=locator,
        )
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO evidence (
                    evidence_id, source_id, version, content_hash, retrieved_at,
                    local_blob_path, media_type, locator_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.evidence_id,
                    record.source_id,
                    record.version,
                    record.content_hash,
                    record.retrieved_at.isoformat(),
                    record.local_blob_path,
                    record.media_type,
                    json.dumps(record.locator),
                ),
            )
        return record

    def find(self, source_id: str, version: str, content_hash: str) -> EvidenceRecord | None:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM evidence
                WHERE source_id = ? AND version = ? AND content_hash = ?
                """,
                (source_id, version, content_hash),
            ).fetchone()
        if row is None:
            return None
        return EvidenceRecord(
            evidence_id=row["evidence_id"],
            source_id=row["source_id"],
            version=row["version"],
            content_hash=row["content_hash"],
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
            local_blob_path=row["local_blob_path"],
            media_type=row["media_type"],
            locator=json.loads(row["locator_json"]),
        )


class ClaimRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_pending(
        self, statement: str, evidence_ids: list[str], created_at: datetime
    ) -> ClaimRecord:
        record = ClaimRecord(
            claim_id=_id(),
            statement=statement,
            review_status=ClaimStatus.PENDING,
            created_at=created_at,
        )
        with self.db.transaction() as connection:
            self._insert_claim(connection, record, evidence_ids)
        return record

    def propose_replacement(
        self,
        original_claim_id: str,
        statement: str,
        evidence_ids: list[str],
        created_at: datetime,
    ) -> ClaimRecord:
        replacement = ClaimRecord(
            claim_id=_id(),
            statement=statement,
            review_status=ClaimStatus.PENDING,
            created_at=created_at,
        )
        with self.db.transaction() as connection:
            self._insert_claim(connection, replacement, evidence_ids)
            connection.execute(
                """
                INSERT INTO claim_relations (from_claim_id, to_claim_id, relation)
                VALUES (?, ?, 'supersedes')
                """,
                (replacement.claim_id, original_claim_id),
            )
        return replacement

    @staticmethod
    def _insert_claim(connection, record: ClaimRecord, evidence_ids: list[str]) -> None:
        connection.execute(
            """
            INSERT INTO claims (claim_id, statement, review_status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                record.claim_id,
                record.statement,
                record.review_status.value,
                record.created_at.isoformat(),
            ),
        )
        connection.executemany(
            "INSERT INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?)",
            [(record.claim_id, evidence_id) for evidence_id in evidence_ids],
        )

    def get(self, claim_id: str) -> ClaimRecord:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        return ClaimRecord(
            claim_id=row["claim_id"],
            statement=row["statement"],
            review_status=ClaimStatus(row["review_status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def evidence_ids(self, claim_id: str) -> list[str]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT evidence_id FROM claim_evidence
                WHERE claim_id = ? ORDER BY evidence_id
                """,
                (claim_id,),
            ).fetchall()
        return [row["evidence_id"] for row in rows]

    def relations_from(self, claim_id: str) -> list[tuple[str, str]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT to_claim_id, relation FROM claim_relations
                WHERE from_claim_id = ? ORDER BY to_claim_id, relation
                """,
                (claim_id,),
            ).fetchall()
        return [(row["to_claim_id"], row["relation"]) for row in rows]

    def count(self) -> int:
        with self.db.connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
