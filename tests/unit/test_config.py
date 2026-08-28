import pytest
from pydantic import ValidationError

from knowledgemap.config import Settings


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_analyzer_accepts_loopback_hosts(host, tmp_path):
    settings = Settings(data_dir=tmp_path, analyzer_base_url=f"http://{host}:11434/v1")
    assert settings.analyzer_base_url


def test_analyzer_rejects_remote_host(tmp_path):
    with pytest.raises(ValidationError, match="loopback"):
        Settings(data_dir=tmp_path, analyzer_base_url="https://api.example.com/v1")

