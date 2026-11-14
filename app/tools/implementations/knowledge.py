"""Read-only knowledge adapters; policy owns authorization before handlers run."""

from datetime import UTC, datetime

from psycopg_pool import PoolClosed, PoolTimeout
from pydantic import Field, field_validator

from app.agents.types import AgentType
from app.knowledge.chunking import token_count
from app.knowledge.models import (
    Contract,
    EvidenceReference,
    KnowledgeError,
    SearchQuery,
    SearchResult,
)
from app.runtime.context import DemoIdentity
from app.tools.models import HandlerResult, ToolDefinition, ToolMetadata, ToolUnavailableError


class SearchKnowledgeArgs(SearchQuery):
    @field_validator("query")
    @classmethod
    def bounded_query(cls, value):
        if not value.strip() or token_count(value) > 512:
            raise ValueError("Query must contain 1..512 tokens")
        return value


class ValidateKnowledgeSourcesArgs(Contract):
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=5)


class SourceValidationResult(Contract):
    valid: bool
    invalid_evidence_ids: list[str]
    safe_code: str | None
    checked_at: datetime


def knowledge_tools(retriever):
    """Only a ready retriever enables the registered tools. No runtime resource creation."""

    async def search(args, context):
        try:
            result = await retriever.search(
                SearchQuery.model_validate(args.model_dump()),
                identity=DemoIdentity(context.user_id, frozenset({"knowledge:read"})),
            )
        except KnowledgeError as error:
            raise ToolUnavailableError("Knowledge retrieval unavailable", code=str(error)) from None
        except (PoolClosed, PoolTimeout):
            raise ToolUnavailableError(
                "Knowledge retrieval unavailable", code="knowledge_unavailable"
            ) from None
        return HandlerResult(data=result)

    async def validate(args, context):
        try:
            result = await retriever.validate_evidence(
                args.evidence,
                identity=DemoIdentity(context.user_id, frozenset({"knowledge:read"})),
            )
        except KnowledgeError as error:
            raise ToolUnavailableError(
                "Knowledge validation unavailable", code=str(error)
            ) from None
        except (PoolClosed, PoolTimeout):
            raise ToolUnavailableError(
                "Knowledge validation unavailable", code="knowledge_unavailable"
            ) from None
        return HandlerResult(
            data=SourceValidationResult(
                **result,
                safe_code=None if result["valid"] else "source_changed",
                checked_at=datetime.now(UTC),
            )
        )

    def metadata(name, description, timeout, retries, tags):
        return ToolMetadata(
            name=name,
            version="1",
            description=description,
            enabled=retriever is not None,
            allowed_agents=frozenset({AgentType.KNOWLEDGE}),
            required_scopes=frozenset({"knowledge:read"}),
            risk_level="low",
            approval_required=False,
            read_only=True,
            has_business_side_effects=False,
            idempotency="not_applicable",
            timeout_seconds=timeout,
            max_retries=retries,
            tags=frozenset(tags),
        )

    return (
        ToolDefinition(
            metadata(
                "search_knowledge",
                "检索公共Demo帮助知识，返回带来源证据",
                15,
                0,
                {"knowledge", "read", "vector"},
            ),
            SearchKnowledgeArgs,
            SearchResult,
            search,
        ),
        ToolDefinition(
            metadata(
                "validate_knowledge_sources",
                "复核本次知识证据的当前版本与内容",
                5,
                1,
                {"knowledge", "source_validation"},
            ),
            ValidateKnowledgeSourcesArgs,
            SourceValidationResult,
            validate,
        ),
    )
