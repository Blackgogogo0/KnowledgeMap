import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel

from knowledgemap.analyzer.base import Analyzer
from knowledgemap.db import Database
from knowledgemap.sessions.service import AuthorizedSession, SessionService


class RecommendationRecord(BaseModel):
    recommendation_id: str
    knowledge_question: str
    why_needed: str
    preferred_source_types: list[str]
    status: str


class SessionAnalysisResult(BaseModel):
    analysis_id: str
    grant_id: str
    goal: str
    existing_knowledge: list[str]
    recommendations: list[RecommendationRecord]
    created_at: datetime


class AnalysisService:
    def __init__(
        self,
        db: Database,
        sessions: SessionService,
        analyzer: Analyzer,
        clock: Callable[[], datetime] | None = None,
    ):
        self.db = db
        self.sessions = sessions
        self.analyzer = analyzer
        self.clock = clock or (lambda: datetime.now(UTC))

    async def analyze_authorized_session(
        self, client: str, session_id: str, confirm_read: bool
    ) -> SessionAnalysisResult:
        authorized = self.sessions.grant_and_read(
            client, session_id, confirm_read=confirm_read, now=self.clock()
        )
        return await self._analyze(authorized)

    async def analyze_existing_grant(
        self, client: str, session_id: str
    ) -> SessionAnalysisResult:
        return await self._analyze(self.sessions.read(client, session_id))

    async def _analyze(
        self, authorized: AuthorizedSession
    ) -> SessionAnalysisResult:
        draft = await self.analyzer.analyze_session(authorized.messages)
        created_at = self.clock()
        analysis_id = str(uuid4())
        recommendations = [
            RecommendationRecord(
                recommendation_id=str(uuid4()),
                knowledge_question=item.knowledge_question,
                why_needed=item.why_needed,
                preferred_source_types=item.preferred_source_types,
                status="pending",
            )
            for item in draft.recommendations
        ]
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO session_analyses (
                    analysis_id, grant_id, goal, existing_knowledge_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    authorized.grant.grant_id,
                    draft.goal,
                    json.dumps(draft.existing_knowledge),
                    created_at.isoformat(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO recommendations (
                    recommendation_id, analysis_id, knowledge_question, why_needed,
                    preferred_source_types_json, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.recommendation_id,
                        analysis_id,
                        item.knowledge_question,
                        item.why_needed,
                        json.dumps(item.preferred_source_types),
                        item.status,
                    )
                    for item in recommendations
                ],
            )
        return SessionAnalysisResult(
            analysis_id=analysis_id,
            grant_id=authorized.grant.grant_id,
            goal=draft.goal,
            existing_knowledge=draft.existing_knowledge,
            recommendations=recommendations,
            created_at=created_at,
        )
