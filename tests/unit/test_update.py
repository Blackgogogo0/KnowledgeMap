from datetime import UTC, datetime, timedelta

import pytest

from knowledgemap.db import Database
from knowledgemap.repository import SourceRepository
from knowledgemap.update import SourceUpdateResult, UpdateService


NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


class FakeChecker:
    def __init__(self, status="unchanged"):
        self.status = status
        self.calls = []

    async def check(self, source):
        self.calls.append(source["source_id"])
        return SourceUpdateResult(source_id=source["source_id"], status=self.status)


def add_policy(db, source_id, policy, last_checked):
    with db.transaction() as connection:
        connection.execute(
            "UPDATE sources SET update_policy = ?, last_checked_at = ? WHERE source_id = ?",
            (policy, last_checked.isoformat() if last_checked else None, source_id),
        )


@pytest.mark.asyncio
async def test_weekly_check_only_runs_due_sources(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    sources = SourceRepository(db)
    due = sources.create("web", "https://example.test/due", NOW)
    fresh = sources.create("web", "https://example.test/fresh", NOW)
    manual = sources.create("web", "https://example.test/manual", NOW)
    add_policy(db, due.source_id, "weekly", NOW - timedelta(days=8))
    add_policy(db, fresh.source_id, "weekly", NOW - timedelta(days=2))
    add_policy(db, manual.source_id, "manual", None)
    checker = FakeChecker()

    result = await UpdateService(db, {"web": checker}).check_due(NOW)

    assert result.checked_ids == [due.source_id]
    assert checker.calls == [due.source_id]


@pytest.mark.asyncio
async def test_manual_check_updates_last_checked_timestamp(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    source = SourceRepository(db).create("web", "https://example.test/doc", NOW)

    result = await UpdateService(db, {"web": FakeChecker()}).check_source(
        source.source_id, NOW
    )

    assert result.status == "unchanged"
    with db.connect() as connection:
        row = connection.execute(
            "SELECT last_checked_at FROM sources WHERE source_id = ?", (source.source_id,)
        ).fetchone()
    assert row["last_checked_at"] == NOW.isoformat()
