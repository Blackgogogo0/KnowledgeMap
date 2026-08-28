from collections import defaultdict
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from knowledgemap.models import ClaimStatus, SearchQuery
from knowledgemap.search import SearchService
from knowledgemap.session_intelligence.filter import normalize_events
from knowledgemap.session_intelligence.models import (
    KnowledgeNeedStatus,
    SessionInsightSubmission,
    TaskStateDelta,
    TaskStateSnapshot,
)
from knowledgemap.session_intelligence.needs import build_needs
from knowledgemap.session_intelligence.repository import (
    AnalysisRecord,
    SessionIntelligenceRepository,
)
from knowledgemap.session_intelligence.router import validate_routes
from knowledgemap.session_intelligence.state import merge_state


class NeedResolution(BaseModel):
    knowledge_need_id: str
    status: KnowledgeNeedStatus
    hits: list[Any]


class SessionIntelligenceService:
    def __init__(self, repository, sessions, analyzer, search: SearchService):
        self.repository: SessionIntelligenceRepository = repository
        self.sessions = sessions
        self.analyzer = analyzer
        self.search = search

    async def submit(
        self,
        submission: SessionInsightSubmission,
        provider_mode: str = "client_assisted",
    ) -> AnalysisRecord:
        latest = self.repository.get_latest_state(submission.client, submission.session_id)
        previous = {state.episode_id: state for state in latest[1]} if latest else {}
        grouped: dict[str, list[TaskStateDelta]] = defaultdict(list)
        for delta in submission.episode_deltas:
            grouped[delta.episode_id].append(delta)
        snapshots = [
            merge_state(previous.get(episode_id), deltas)
            for episode_id, deltas in grouped.items()
        ]
        if not snapshots:
            snapshots = list(previous.values())
        route_ids = [route.unresolved_item_id for route in submission.routes]
        validate_routes(route_ids, submission.routes)
        filtered_needs = build_needs(submission.routes, submission.knowledge_needs)
        normalized = submission.model_copy(update={"knowledge_needs": filtered_needs})
        return self.repository.commit_submission(normalized, snapshots, provider_mode)

    async def prepare_local(
        self, client: str, session_id: str, confirm_read: bool
    ) -> AnalysisRecord:
        if self.analyzer is None:
            raise RuntimeError("A local analyzer is required.")
        from datetime import UTC, datetime

        authorized = self.sessions.grant_and_read(
            client, session_id, confirm_read=confirm_read, now=datetime.now(UTC)
        )
        latest = self.repository.get_latest_state(client, session_id)
        previous_checkpoint = latest[0] if latest else None
        previous_states = latest[1] if latest else []
        last_message_id = None
        if previous_checkpoint:
            with self.repository.db.connect() as connection:
                row = connection.execute(
                    "SELECT last_message_id FROM session_checkpoints WHERE checkpoint_id = ?",
                    (previous_checkpoint.checkpoint_id,),
                ).fetchone()
                last_message_id = row["last_message_id"]
        events = normalize_events(authorized.messages, last_message_id)
        previous_state = previous_states[-1] if previous_states else None
        state_draft = await self.analyzer.extract_state(events, previous_state)
        snapshots = self._merge_deltas(previous_states, state_draft.deltas)
        state = snapshots[-1] if snapshots else previous_state
        routes = [] if state is None else (await self.analyzer.route_gaps(state)).routes
        validate_routes(state_draft.unresolved_item_ids, routes)
        needs = [] if state is None else (await self.analyzer.compose_needs(state, routes)).knowledge_needs
        last_id = events[-1].message_id if events else last_message_id
        submission = SessionInsightSubmission(
            client=client,
            session_id=session_id,
            checkpoint_id=str(uuid4()),
            previous_checkpoint_id=(previous_checkpoint.checkpoint_id if previous_checkpoint else None),
            last_message_id=last_id,
            content_hash=sha256(
                "\n".join(event.model_dump_json() for event in events).encode()
            ).hexdigest(),
            episode_deltas=state_draft.deltas,
            routes=routes,
            knowledge_needs=build_needs(routes, needs),
        )
        return self.repository.commit_submission(submission, snapshots, "local_ollama")

    @staticmethod
    def _merge_deltas(
        previous_states: list[TaskStateSnapshot], deltas: list[TaskStateDelta]
    ) -> list[TaskStateSnapshot]:
        previous = {state.episode_id: state for state in previous_states}
        grouped: dict[str, list[TaskStateDelta]] = defaultdict(list)
        for delta in deltas:
            grouped[delta.episode_id].append(delta)
        for episode_id, episode_deltas in grouped.items():
            previous[episode_id] = merge_state(previous.get(episode_id), episode_deltas)
        return list(previous.values())

    def get_analysis(self, client: str, session_id: str):
        return self.repository.get_latest_state(client, session_id)

    def list_needs(self, **filters):
        return self.repository.list_needs(**filters)

    def resolve_need(self, need_id: str) -> NeedResolution:
        rows = self.repository.list_needs(top_k=1000)
        need = next((row for row in rows if row["knowledge_need_id"] == need_id), None)
        if need is None:
            from knowledgemap.errors import KnowledgeMapError

            raise KnowledgeMapError("KNOWLEDGE_NEED_NOT_FOUND", "Knowledge Need was not found.")
        accepted = self.search.search(SearchQuery(query=need["question"], top_k=5))
        if accepted:
            self.repository.attach_resolution(need_id, [hit.claim_id for hit in accepted])
            self.repository.set_need_status(need_id, KnowledgeNeedStatus.RESOLVED)
            return NeedResolution(
                knowledge_need_id=need_id,
                status=KnowledgeNeedStatus.RESOLVED,
                hits=accepted,
            )
        stale = self.search.search(
            SearchQuery(
                query=need["question"],
                top_k=5,
                statuses=[ClaimStatus.DISPUTED, ClaimStatus.STALE_CANDIDATE],
            )
        )
        status = KnowledgeNeedStatus.NEEDS_REFRESH if stale else KnowledgeNeedStatus.OPEN
        self.repository.set_need_status(need_id, status)
        return NeedResolution(knowledge_need_id=need_id, status=status, hits=stale)

