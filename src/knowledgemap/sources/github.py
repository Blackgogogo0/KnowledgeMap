import base64
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from urllib.parse import quote
from uuid import uuid4

import httpx

from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError


@dataclass(frozen=True)
class ManifestDiff:
    added: list[str]
    modified: list[str]
    deleted: list[str]
    renamed: dict[str, str]


class RepositoryContinuity(StrEnum):
    CONTINUOUS = "continuous"
    DEFAULT_BRANCH_CHANGED = "default-branch-changed"
    FORCE_PUSH_OR_NO_COMMON_ANCESTOR = "force-push-or-no-common-ancestor"


class GitHubSourceAdapter:
    api_base = "https://api.github.com"
    text_extensions = {
        ".md", ".markdown", ".txt", ".rst", ".adoc", ".py", ".js",
        ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".json", ".yaml", ".yml",
    }
    excluded_parts = {".git", "node_modules", "vendor", "dist", "build", ".venv"}
    excluded_names = {
        "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock",
    }

    def __init__(
        self,
        token: str | None = None,
        max_files: int = 500,
        max_total_bytes: int = 20 * 1024 * 1024,
        timeout: float = 20.0,
    ):
        self.token = token
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes
        self.timeout = httpx.Timeout(timeout, connect=min(timeout, 10.0))

    @property
    def headers(self) -> dict[str, str]:
        result = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            result["Authorization"] = f"Bearer {self.token}"
        return result

    async def resolve_ref(self, owner: str, repo: str, ref: str) -> str:
        data = await self._get_json(f"/repos/{owner}/{repo}/commits/{quote(ref, safe='')}")
        try:
            return data["sha"]
        except (KeyError, TypeError) as error:
            raise KnowledgeMapError("GITHUB_INVALID_RESPONSE", "GitHub commit response has no SHA.") from error

    async def fetch_manifest(self, owner: str, repo: str, commit: str) -> dict[str, str]:
        data = await self._get_json(
            f"/repos/{owner}/{repo}/git/trees/{commit}", params={"recursive": "1"}
        )
        if data.get("truncated"):
            raise KnowledgeMapError("GITHUB_TREE_TRUNCATED", "GitHub tree exceeded API limits.")
        return {
            item["path"]: item["sha"]
            for item in data.get("tree", [])
            if item.get("type") == "blob" and item.get("path") and item.get("sha")
        }

    async def fetch_files(
        self,
        owner: str,
        repo: str,
        manifest: dict[str, str],
        mode: str,
        selected_paths: list[str] | None = None,
    ) -> dict[str, str]:
        paths = self.select_paths(list(manifest), mode, selected_paths)
        if len(paths) > self.max_files:
            raise KnowledgeMapError("GITHUB_FILE_LIMIT", "Selected files exceed the configured limit.")
        files: dict[str, str] = {}
        total = 0
        for path in paths:
            data = await self._get_json(f"/repos/{owner}/{repo}/git/blobs/{manifest[path]}")
            if data.get("encoding") != "base64":
                raise KnowledgeMapError("GITHUB_INVALID_RESPONSE", "GitHub blob is not base64 encoded.")
            try:
                raw = base64.b64decode(data["content"], validate=True)
                text = raw.decode("utf-8")
            except (KeyError, ValueError, UnicodeDecodeError) as error:
                raise KnowledgeMapError("GITHUB_NON_TEXT_BLOB", f"GitHub blob is not UTF-8 text: {path}") from error
            total += len(raw)
            if total > self.max_total_bytes:
                raise KnowledgeMapError("GITHUB_BYTE_LIMIT", "Selected files exceed the byte limit.")
            files[path] = text
        return files

    def select_paths(
        self,
        paths: list[str],
        mode: str,
        selected_paths: list[str] | None = None,
    ) -> list[str]:
        def safe(path: str) -> bool:
            value = PurePosixPath(path)
            return (
                not any(part in self.excluded_parts for part in value.parts)
                and value.name not in self.excluded_names
                and value.suffix.lower() in self.text_extensions
            )

        candidates = [path for path in sorted(paths) if safe(path)]
        if mode == "docs-only":
            return [
                path for path in candidates
                if PurePosixPath(path).name.lower().startswith("readme")
                or path.lower().startswith("docs/")
            ]
        if mode == "selected-paths":
            selected = set(selected_paths or [])
            return [path for path in candidates if path in selected]
        if mode == "whole-repo":
            return candidates
        raise KnowledgeMapError("GITHUB_IMPORT_MODE_INVALID", f"Unsupported GitHub mode: {mode}")

    @staticmethod
    def stable_url(
        owner: str, repo: str, commit: str, path: str, line_start: int, line_end: int
    ) -> str:
        encoded_path = quote(path, safe="/")
        return f"https://github.com/{owner}/{repo}/blob/{commit}/{encoded_path}#L{line_start}-L{line_end}"

    @staticmethod
    def compare(old: dict[str, str], new: dict[str, str]) -> ManifestDiff:
        old_paths, new_paths = set(old), set(new)
        deleted = sorted(old_paths - new_paths)
        added = sorted(new_paths - old_paths)
        renamed: dict[str, str] = {}
        for old_path in list(deleted):
            matches = [new_path for new_path in added if new[new_path] == old[old_path]]
            if matches:
                new_path = matches[0]
                renamed[old_path] = new_path
                deleted.remove(old_path)
                added.remove(new_path)
        modified = sorted(path for path in old_paths & new_paths if old[path] != new[path])
        return ManifestDiff(added=added, modified=modified, deleted=deleted, renamed=renamed)

    @staticmethod
    def propose_impacts(
        db: Database, source_id: str, diff: ManifestDiff, now: datetime
    ) -> list[str]:
        affected = sorted(set(diff.modified + diff.deleted))
        if not affected:
            return []
        placeholders = ",".join("?" for _ in affected)
        with db.transaction() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT ce.claim_id FROM claim_evidence ce
                JOIN evidence e ON e.evidence_id = ce.evidence_id
                WHERE e.source_id = ?
                  AND json_extract(e.locator_json, '$.path') IN ({placeholders})
                ORDER BY ce.claim_id
                """,
                (source_id, *affected),
            ).fetchall()
            claim_ids = [row["claim_id"] for row in rows]
            connection.executemany(
                """
                INSERT INTO review_items (
                    review_item_id, target_type, target_id, proposed_action,
                    note, status, created_at
                ) VALUES (?, 'claim', ?, 'stale_candidate', ?, 'pending', ?)
                """,
                [
                    (
                        str(uuid4()), claim_id,
                        "GitHub evidence path changed or was deleted.", now.isoformat(),
                    )
                    for claim_id in claim_ids
                ],
            )
        return claim_ids

    async def repository_state(self, owner: str, repo: str) -> dict[str, object]:
        data = await self._get_json(f"/repos/{owner}/{repo}")
        return {
            "default_branch": data.get("default_branch"),
            "archived": bool(data.get("archived")),
            "status": "archived" if data.get("archived") else "available",
        }

    @staticmethod
    def assess_continuity(
        previous_default_branch: str,
        current_default_branch: str,
        comparison_status: str,
    ) -> RepositoryContinuity:
        if previous_default_branch != current_default_branch:
            return RepositoryContinuity.DEFAULT_BRANCH_CHANGED
        if comparison_status in {"diverged", "no-common-ancestor"}:
            return RepositoryContinuity.FORCE_PUSH_OR_NO_COMMON_ANCESTOR
        return RepositoryContinuity.CONTINUOUS

    async def compare_commits(
        self, owner: str, repo: str, previous_commit: str, current_commit: str
    ) -> str:
        url = (
            f"{self.api_base}/repos/{owner}/{repo}/compare/"
            f"{quote(previous_commit, safe='')}...{quote(current_commit, safe='')}"
        )
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            response = await client.get(url)
        if response.status_code == 404:
            try:
                message = response.json().get("message", "")
            except ValueError:
                message = ""
            if "common ancestor" in message.lower():
                return "no-common-ancestor"
            raise KnowledgeMapError("GITHUB_NOT_FOUND", "GitHub repository or commit was not found.")
        if response.status_code in {401, 403}:
            raise KnowledgeMapError("GITHUB_AUTHORIZATION_FAILED", "GitHub authorization failed.")
        if response.status_code >= 500:
            raise KnowledgeMapError("GITHUB_UNAVAILABLE", "GitHub is temporarily unavailable.")
        if response.is_error:
            raise KnowledgeMapError("GITHUB_REQUEST_FAILED", f"GitHub returned HTTP {response.status_code}.")
        status = response.json().get("status")
        if status not in {"ahead", "behind", "diverged", "identical"}:
            raise KnowledgeMapError("GITHUB_INVALID_RESPONSE", "GitHub comparison status is invalid.")
        return status

    @staticmethod
    def propose_conflicts(
        db: Database, claim_ids: list[str], now: datetime
    ) -> list[str]:
        unique_ids = sorted(set(claim_ids))
        if not unique_ids:
            return []
        placeholders = ",".join("?" for _ in unique_ids)
        with db.transaction() as connection:
            rows = connection.execute(
                f"SELECT claim_id FROM claims WHERE claim_id IN ({placeholders}) ORDER BY claim_id",
                unique_ids,
            ).fetchall()
            existing = [row["claim_id"] for row in rows]
            connection.executemany(
                """
                INSERT INTO review_items (
                    review_item_id, target_type, target_id, proposed_action,
                    note, status, created_at
                ) VALUES (?, 'claim', ?, 'disputed', ?, 'pending', ?)
                """,
                [
                    (
                        str(uuid4()), claim_id,
                        "New GitHub evidence may contradict this accepted claim.",
                        now.isoformat(),
                    )
                    for claim_id in existing
                ],
            )
        return existing

    async def _get_json(self, path: str, params: dict[str, str] | None = None):
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            response = await client.get(f"{self.api_base}{path}", params=params)
        if response.status_code == 404:
            raise KnowledgeMapError("GITHUB_NOT_FOUND", "GitHub repository or object was not found.")
        if response.status_code in {401, 403}:
            raise KnowledgeMapError("GITHUB_AUTHORIZATION_FAILED", "GitHub authorization failed.")
        if response.status_code >= 500:
            raise KnowledgeMapError("GITHUB_UNAVAILABLE", "GitHub is temporarily unavailable.")
        if response.is_error:
            raise KnowledgeMapError("GITHUB_REQUEST_FAILED", f"GitHub returned HTTP {response.status_code}.")
        return response.json()
