from pydantic import BaseModel, Field


class FetchedSource(BaseModel):
    canonical_uri: str
    raw: bytes
    text: str
    media_type: str
    version: str
    retrieval: dict[str, object] = Field(default_factory=dict)
