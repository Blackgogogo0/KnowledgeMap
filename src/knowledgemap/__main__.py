import argparse
import asyncio
from datetime import UTC, datetime

from knowledgemap.config import Settings
from knowledgemap.db import Database
from knowledgemap.mcp_server import KnowledgeMapApplication, build_server


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="knowledgemap")
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("serve", help="Run the MCP server over stdio")
    subcommands.add_parser("migrate", help="Create or upgrade the local database")
    subcommands.add_parser("check-updates", help="Check weekly sources that are due")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = Settings()
    if args.command == "serve":
        build_server(settings).run("stdio")
    elif args.command == "migrate":
        Database(settings.database_path).migrate()
    elif args.command == "check-updates":
        app = KnowledgeMapApplication(settings)
        asyncio.run(app.updates.check_due(datetime.now(UTC)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
