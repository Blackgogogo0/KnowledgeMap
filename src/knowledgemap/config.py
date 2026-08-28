from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KNOWLEDGEMAP_",
        env_file=".env",
        extra="ignore",
    )

    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "share" / "knowledgemap"
    )
    claude_session_root: Path = Field(
        default_factory=lambda: Path.home() / ".claude" / "projects"
    )
    codex_session_root: Path = Field(
        default_factory=lambda: Path.home() / ".codex" / "sessions"
    )
    analyzer_base_url: str = "http://127.0.0.1:11434/v1"
    analyzer_model: str = "qwen3.5:0.8b"
    analyzer_api_key: str | None = None
    github_token: str | None = None
    local_source_root: Path = Field(default_factory=Path.cwd)
    update_interval_days: int = Field(default=7, ge=1)

    @field_validator("analyzer_base_url")
    @classmethod
    def analyzer_must_be_loopback(cls, value: str) -> str:
        hostname = urlparse(value).hostname
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("analyzer must use a loopback host")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir / "knowledge.db"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"
