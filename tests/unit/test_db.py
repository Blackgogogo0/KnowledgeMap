from knowledgemap.db import Database


def test_migrate_creates_claim_and_fts_tables(tmp_path):
    db = Database(tmp_path / "knowledge.db")

    db.migrate()

    with db.connect() as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
    assert {"sources", "evidence", "claims", "claim_evidence", "claims_fts"} <= names


def test_migrate_is_idempotent(tmp_path):
    db = Database(tmp_path / "knowledge.db")

    db.migrate()
    db.migrate()

    with db.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1


def test_connect_enables_foreign_keys_and_wal(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()

    with db.connect() as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert foreign_keys == 1
    assert journal_mode == "wal"
