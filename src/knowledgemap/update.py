import json
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError


UpdateStatus = Literal["unchanged", "changed", "failed", "source_unavailable"]


class SourceUpdateResult(BaseModel):
    source_id: str
    status: UpdateStatus
    details: dict[str, object] = Field(default_factory=dict)


class UpdateRunResult(BaseModel):
    run_id: str
    checked_ids: list[str]
    results: list[SourceUpdateResult]

    @property
    def failed_count(self) -> int:
        return sum(item.status in {"failed", "source_unavailable"} for item in self.results)

    @property
    def succeeded_count(self) -> int:
        return len(self.results) - self.failed_count


class SourceChecker(Protocol):
    async def check(self, source) -> SourceUpdateResult: ...


class UpdateService:
    def __init__(
        self,
        db: Database,
        checkers: dict[str, SourceChecker],
        interval_days: int = 7,
    ):
        self.db = db
        self.checkers = checkers
        self.interval_days = interval_days

    async def check_source(
        self, source_id: str, now: datetime
    ) -> SourceUpdateResult:
        run_id = self._start_run(now)
        try:
            source = self._get_source(source_id)
            result = await self._check_one(source, now)
            self._store_result(run_id, result)
            self._finish_run(run_id, now, "completed")
            return result
        except Exception:
            self._finish_run(run_id, now, "failed")
            raise

    async def check_due(self, now: datetime) -> UpdateRunResult:
        cutoff = (now - timedelta(days=self.interval_days)).isoformat()
        with self.db.connect() as connection:
            sources = connection.execute(
                """
                SELECT * FROM sources
                WHERE update_policy = 'weekly'
                  AND (last_checked_at IS NULL OR last_checked_at <= ?)
                ORDER BY source_id
                """,
                (cutoff,),
            ).fetchall()
        run_id = self._start_run(now)
        results: list[SourceUpdateResult] = []
        for source in sources:
            try:
                result = await self._check_one(source, now)
            except Exception as error:
                unavailable = isinstance(error, KnowledgeMapError) and error.code in {
                    "GITHUB_NOT_FOUND", "GITHUB_UNAVAILABLE", "SOURCE_NOT_FOUND"
                }
                result = SourceUpdateResult(
                    source_id=source["source_id"],
                    status="source_unavailable" if unavailable else "failed",
                    details={"error_type": type(error).__name__},
                )
                self._mark_checked(source["source_id"], now, result.status)
            self._store_result(run_id, result)
            results.append(result)
        status = "completed" if not any(
            item.status in {"failed", "source_unavailable"} for item in results
        ) else "partial"
        self._finish_run(run_id, now, status)
        return UpdateRunResult(
            run_id=run_id,
            checked_ids=[source["source_id"] for source in sources],
            results=results,
        )

    async def _check_one(self, source, now: datetime) -> SourceUpdateResult:
        try:
            checker = self.checkers[source["type"]]
        except KeyError as error:
            raise KnowledgeMapError(
                "UPDATE_CHECKER_NOT_FOUND", f"No update checker for source type: {source['type']}"
            ) from error
        result = await checker.check(source)
        if result.source_id != source["source_id"]:
            raise KnowledgeMapError("UPDATE_RESULT_INVALID", "Checker returned a different source ID.")
        self._mark_checked(source["source_id"], now, "available")
        return result

    def _get_source(self, source_id: str):
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE source_id = ?", (source_id,)
            ).fetchone()
        if row is None:
            raise KnowledgeMapError("SOURCE_NOT_FOUND", "Source was not found.")
        return row

    def _mark_checked(self, source_id: str, now: datetime, availability: str) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                """
                UPDATE sources SET last_checked_at = ?, availability_status = ?
                WHERE source_id = ?
                """,
                (now.isoformat(), availability, source_id),
            )

    def _start_run(self, now: datetime) -> str:
        run_id = str(uuid4())
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO update_runs (run_id, started_at, status) VALUES (?, ?, 'running')",
                (run_id, now.isoformat()),
            )
        return run_id

    def _finish_run(self, run_id: str, now: datetime, status: str) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE update_runs SET finished_at = ?, status = ? WHERE run_id = ?",
                (now.isoformat(), status, run_id),
            )

    def _store_result(self, run_id: str, result: SourceUpdateResult) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO update_results (result_id, run_id, source_id, status, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid4()), run_id, result.source_id, result.status, json.dumps(result.details)),
            )
