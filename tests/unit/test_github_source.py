import base64

import pytest

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sources.github import GitHubSourceAdapter, RepositoryContinuity


@pytest.fixture
def github_adapter():
    return GitHubSourceAdapter()


def test_docs_only_filters_manifest(github_adapter):
    paths = github_adapter.select_paths(
        ["README.md", "docs/auth.md", "src/app.py", "vendor/lib.js"],
        mode="docs-only",
    )
    assert paths == ["README.md", "docs/auth.md"]


def test_selected_and_whole_repo_apply_exclusions(github_adapter):
    paths = ["docs/a.md", "src/app.py", "node_modules/a.js", "package-lock.json"]
    assert github_adapter.select_paths(
        paths, mode="selected-paths", selected_paths=["src/app.py"]
    ) == ["src/app.py"]
    assert github_adapter.select_paths(paths, mode="whole-repo") == [
        "docs/a.md",
        "src/app.py",
    ]


def test_stable_url_is_commit_pinned(github_adapter):
    assert github_adapter.stable_url("o", "r", "abc123", "docs/a.md", 4, 9) == (
        "https://github.com/o/r/blob/abc123/docs/a.md#L4-L9"
    )


def test_compare_classifies_changes_and_same_hash_rename(github_adapter):
    old = {
        "README.md": "sha-a",
        "docs/old.md": "same",
        "docs/deleted.md": "gone",
    }
    new = {
        "README.md": "sha-b",
        "docs/new-name.md": "same",
        "docs/added.md": "new",
    }

    diff = github_adapter.compare(old, new)

    assert diff.modified == ["README.md"]
    assert diff.added == ["docs/added.md"]
    assert diff.deleted == ["docs/deleted.md"]
    assert diff.renamed == {"docs/old.md": "docs/new-name.md"}


@pytest.mark.asyncio
async def test_resolve_manifest_and_fetch_utf8_blobs(respx_mock):
    adapter = GitHubSourceAdapter(token="token")
    respx_mock.get("https://api.github.com/repos/o/r/commits/main").respond(
        json={"sha": "abc123"}
    )
    respx_mock.get("https://api.github.com/repos/o/r/git/trees/abc123?recursive=1").respond(
        json={"tree": [{"type": "blob", "path": "docs/a.md", "sha": "blob1", "size": 5}]}
    )
    respx_mock.get("https://api.github.com/repos/o/r/git/blobs/blob1").respond(
        json={"encoding": "base64", "content": base64.b64encode(b"hello").decode()}
    )

    commit = await adapter.resolve_ref("o", "r", "main")
    manifest = await adapter.fetch_manifest("o", "r", commit)
    files = await adapter.fetch_files("o", "r", manifest, mode="docs-only")

    assert commit == "abc123"
    assert manifest == {"docs/a.md": "blob1"}
    assert files == {"docs/a.md": "hello"}


@pytest.mark.asyncio
async def test_github_status_codes_are_distinct(respx_mock):
    adapter = GitHubSourceAdapter()
    respx_mock.get("https://api.github.com/repos/o/missing/commits/main").respond(status_code=404)
    with pytest.raises(KnowledgeMapError, match="GITHUB_NOT_FOUND"):
        await adapter.resolve_ref("o", "missing", "main")


@pytest.mark.asyncio
async def test_repository_state_reports_archived_and_default_branch(respx_mock):
    respx_mock.get("https://api.github.com/repos/o/r").respond(
        json={"archived": True, "default_branch": "trunk"}
    )

    state = await GitHubSourceAdapter().repository_state("o", "r")

    assert state == {
        "default_branch": "trunk",
        "archived": True,
        "status": "archived",
    }


def test_continuity_distinguishes_force_push_and_default_branch_change(github_adapter):
    assert github_adapter.assess_continuity(
        previous_default_branch="main",
        current_default_branch="main",
        comparison_status="diverged",
    ) == RepositoryContinuity.FORCE_PUSH_OR_NO_COMMON_ANCESTOR
    assert github_adapter.assess_continuity(
        previous_default_branch="main",
        current_default_branch="trunk",
        comparison_status="ahead",
    ) == RepositoryContinuity.DEFAULT_BRANCH_CHANGED
    assert github_adapter.assess_continuity(
        previous_default_branch="main",
        current_default_branch="main",
        comparison_status="identical",
    ) == RepositoryContinuity.CONTINUOUS


@pytest.mark.asyncio
async def test_compare_commits_reports_no_common_ancestor(respx_mock):
    respx_mock.get("https://api.github.com/repos/o/r/compare/old...new").respond(
        status_code=404,
        json={"message": "No common ancestor between old and new"},
    )

    status = await GitHubSourceAdapter().compare_commits("o", "r", "old", "new")

    assert status == "no-common-ancestor"


@pytest.mark.asyncio
async def test_authorization_and_unavailability_are_distinct(respx_mock):
    adapter = GitHubSourceAdapter()
    respx_mock.get("https://api.github.com/repos/o/private/commits/main").respond(
        status_code=403
    )
    respx_mock.get("https://api.github.com/repos/o/down/commits/main").respond(
        status_code=503
    )
    with pytest.raises(KnowledgeMapError, match="GITHUB_AUTHORIZATION_FAILED"):
        await adapter.resolve_ref("o", "private", "main")
    with pytest.raises(KnowledgeMapError, match="GITHUB_UNAVAILABLE"):
        await adapter.resolve_ref("o", "down", "main")
