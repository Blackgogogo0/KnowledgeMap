from datetime import UTC, datetime

import pytest

from knowledgemap.db import Database
from knowledgemap.repository import SourceRepository
from knowledgemap.update import SourceUpdateResult, UpdateService


NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


class IsolatedChecker:
    async def check(self, source):
        if source["canonical_uri"].endswith("broken"):
            raise RuntimeError("upstream unavailable")
        return SourceUpdateResult(source_id=source["source_id"], status="changed")


@pytest.mark.asyncio
async def test_one_failure_does_not_block_other_sources(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    sources = SourceRepository(db)
    good = sources.create("web", "https://example.test/good", NOW)
    broken = sources.create("web", "https://example.test/broken", NOW)
    with db.transaction() as connection:
        connection.execute("UPDATE sources SET update_policy = 'weekly'")

    result = await UpdateService(db, {"web": IsolatedChecker()}).check_due(NOW)

    assert result.succeeded_count == 1
    assert result.failed_count == 1
    assert set(result.checked_ids) == {good.source_id, broken.source_id}
    with db.connect() as connection:
        rows = connection.execute("SELECT status FROM update_results ORDER BY status").fetchall()
        accepted_count = connection.execute(
            "SELECT COUNT(*) FROM claims WHERE review_status = 'accepted'"
        ).fetchone()[0]
    assert [row["status"] for row in rows] == ["changed", "failed"]
    assert accepted_count == 0
