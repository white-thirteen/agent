"""Owned resources are closed on normal exit and partial startup failure."""

from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infrastructure.model import model_resources
from app.infrastructure.postgres import DatabaseUnavailableError, open_pool
from app.main import create_app


class EmptySessionPool:
    """Resource fixture with no persisted sessions for the real cutover check."""

    @asynccontextmanager
    async def connection(self):
        yield self

    async def execute(self, query):
        assert query == "SELECT user_id,conversation_id,thread_id FROM sessions"
        return self

    async def fetchall(self):
        return []


async def test_model_transports_close_on_success_and_initialization_failure(monkeypatch):
    import app.infrastructure.model as module

    settings = Settings(_env_file=None, model_name="controlled", model_api_key="test")
    async with model_resources(settings) as (model, _):
        sync_client, async_client = model.http_client, model.http_async_client
        assert model.max_retries == 0
        assert not async_client.is_closed
    assert sync_client.is_closed and async_client.is_closed
    captured = []

    def fail(**kwargs):
        captured.extend((kwargs["http_client"], kwargs["http_async_client"]))
        raise TypeError("programming error")

    monkeypatch.setattr(module, "ChatOpenAI", fail)
    with pytest.raises(TypeError):
        async with model_resources(settings):
            pass
    assert all(client.is_closed for client in captured)


async def test_pool_failure_closes_and_programming_errors_propagate(monkeypatch):
    import app.infrastructure.postgres as module

    instances = []

    class FailedPool:
        failure = TimeoutError()

        def __init__(self, **kwargs):
            self.closed = False
            instances.append(self)

        async def open(self):
            pass

        async def wait(self, **kwargs):
            raise self.failure

        async def close(self):
            self.closed = True

    monkeypatch.setattr(module, "AsyncConnectionPool", FailedPool)
    settings = Settings(_env_file=None, database_url="postgresql://app:unused@localhost/agent_demo")
    with pytest.raises(DatabaseUnavailableError):
        await open_pool(settings)
    FailedPool.failure = TypeError("programming error")
    with pytest.raises(TypeError):
        await open_pool(settings)
    assert all(pool.closed for pool in instances)


def test_lifespan_closes_pool_when_later_resource_fails(monkeypatch):
    import app.main as module

    class Pool:
        closed = False

        async def close(self):
            self.closed = True

    pool = Pool()

    async def opened(settings):
        return pool

    @asynccontextmanager
    async def failed(settings):
        raise TypeError("model initialization failed")
        yield

    monkeypatch.setattr(module, "open_pool", opened)
    monkeypatch.setattr(module, "open_checkpoint_pool", opened)
    monkeypatch.setattr(module, "model_resources", failed)
    settings = Settings(
        _env_file=None,
        database_url="postgresql://app:unused@localhost/agent_demo",
        model_name="controlled",
        model_api_key="test",
    )
    with pytest.raises(TypeError), TestClient(create_app(settings)):
        pass
    assert pool.closed


async def test_shutdown_settles_execution_before_model_and_pool_close(monkeypatch):
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver
    from runtime_support import ControlledModel, MemorySessions, clarify, context

    import app.main as module
    from app.runtime.context import SubmitOptions
    from app.runtime.model_gateway import ModelCallLimits, ModelGateway

    events = []
    entered = asyncio.Event()

    async def blocked(messages):
        entered.set()
        await asyncio.Event().wait()
        return clarify()

    gateway = ModelGateway(ControlledModel([blocked]), ModelCallLimits(8, 30, 0))

    class Pool(EmptySessionPool):
        closed = False

        async def close(self):
            self.closed = True
            events.append("pool_closed")

    pool = Pool()

    async def opened(settings):
        return pool

    original = model_resources
    captured = []

    @asynccontextmanager
    async def controlled_resources(settings):
        async with original(settings) as (raw, _):
            captured.append(raw)
            yield raw, gateway
            assert app.state.agent_runtime._stopping
            assert all(record.task.done() for record in app.state.agent_runtime._records.values())
            assert not raw.http_client.is_closed and not pool.closed
            events.append("runtime_settled")
        events.append("model_closed")

    monkeypatch.setattr(module, "open_pool", opened)

    class CheckpointPool:
        async def close(self):
            events.append("checkpoint_closed")

    async def checkpoint_opened(settings):
        return CheckpointPool()

    monkeypatch.setattr(module, "open_checkpoint_pool", checkpoint_opened)
    monkeypatch.setattr(module, "AsyncPostgresSaver", lambda pool, **kwargs: InMemorySaver())
    monkeypatch.setattr(module, "model_resources", controlled_resources)

    @asynccontextmanager
    async def controlled_store(settings):
        events.append("store_opened")
        yield object()
        assert app.state.agent_runtime._stopping
        assert all(record.task.done() for record in app.state.agent_runtime._records.values())
        assert not captured[0].http_async_client.is_closed
        events.append("store_closed")

    class Embeddings:
        profile = type("Profile", (), {"key": "controlled"})()

        async def initialize(self):
            events.append("embedding_opened")

        async def aclose(self):
            events.append("embedding_closed")

    class Repository:
        def __init__(self, pool):
            pass

        async def check_ready(self, profile):
            assert profile == "controlled"

    monkeypatch.setattr(module, "store_resources", controlled_store)
    monkeypatch.setattr(module, "create_embeddings", lambda settings: Embeddings())
    monkeypatch.setattr(module, "KnowledgeRepository", Repository)
    monkeypatch.setattr(module, "SessionRepository", lambda pool: MemorySessions())
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            model_name="controlled",
            model_api_key="test",
            database_url="postgresql://test:unused@localhost/agent_demo_test",
            runtime_shutdown_grace_seconds=0.01,
            embedding_enabled=True,
        )
    )
    async with app.router.lifespan_context(app):
        handle = await app.state.agent_runtime.submit(context(), options=SubmitOptions())
        await entered.wait()
    assert events == [
        "embedding_opened",
        "store_opened",
        "store_closed",
        "embedding_closed",
        "runtime_settled",
        "model_closed",
        "checkpoint_closed",
        "pool_closed",
    ]
    assert captured[0].http_client.is_closed and captured[0].http_async_client.is_closed
    assert app.state.agent_runtime._records[handle.run_id].error["code"] == "run_interrupted"


def test_pool_log_filter_is_installed_outside_lifespan_and_hides_driver_detail():
    import logging

    from app.infrastructure.postgres import SafePoolLogFilter, install_safe_pool_log_filter

    install_safe_pool_log_filter()
    logger = logging.getLogger("psycopg.pool")
    selected = [item for item in logger.filters if isinstance(item, SafePoolLogFilter)]
    assert len(selected) == 1
    record = logging.LogRecord(
        "psycopg.pool", logging.WARNING, "", 0, "connection failed: %s", ("sensitive",), None
    )
    assert selected[0].filter(record)
    assert record.getMessage() == "PostgreSQL pool resource event"


@pytest.mark.parametrize(
    "failure", ["database", "checkpoint", "embedding", "knowledge", "store", "graph"]
)
async def test_assembly_optional_failures_and_partial_cleanup(monkeypatch, failure):
    """Actual builders/registry run once; failed optional resources do not disable orders."""
    import httpx
    from langgraph.checkpoint.memory import InMemorySaver

    import app.main as module
    from app.knowledge.models import KnowledgeError

    events, builds = [], []

    class Pool(EmptySessionPool):
        def __init__(self, name):
            self.name = name

        async def close(self):
            events.append(self.name)

    async def database(settings):
        if failure == "database":
            raise DatabaseUnavailableError("private DSN must never escape")
        return Pool("database")

    async def checkpoint(settings):
        if failure == "checkpoint":
            raise DatabaseUnavailableError("private DSN must never escape")
        return Pool("checkpoint")

    @asynccontextmanager
    async def model(settings):
        builds.append("model")
        try:
            yield object(), object()
        finally:
            events.append("model")

    class Embeddings:
        profile = type("Profile", (), {"key": "controlled"})()

        async def initialize(self):
            if failure == "embedding":
                raise KnowledgeError("embedding_unavailable")

        async def aclose(self):
            events.append("embedding")

    class Repository:
        def __init__(self, pool):
            pass

        async def check_ready(self, profile):
            if failure == "knowledge":
                raise KnowledgeError("embedding_profile_mismatch")

    @asynccontextmanager
    async def store(settings):
        if failure == "store":
            raise DatabaseUnavailableError("private DSN must never escape")
        try:
            yield object()
        finally:
            events.append("store")

    original = module.build_supervisor_graph

    def graph(**kwargs):
        builds.append("graph")
        if failure == "graph":
            raise TypeError("controlled construction error")
        return original(**kwargs)

    monkeypatch.setattr(module, "open_pool", database)
    monkeypatch.setattr(module, "open_checkpoint_pool", checkpoint)
    monkeypatch.setattr(module, "model_resources", model)
    monkeypatch.setattr(module, "create_embeddings", lambda settings: Embeddings())
    monkeypatch.setattr(module, "KnowledgeRepository", Repository)
    monkeypatch.setattr(module, "store_resources", store)
    monkeypatch.setattr(module, "AsyncPostgresSaver", lambda *args, **kwargs: InMemorySaver())
    monkeypatch.setattr(module, "build_supervisor_graph", graph)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            model_name="controlled",
            model_api_key="test",
            database_url="postgresql://test:unused@localhost/agent_demo_test",
            embedding_enabled=True,
        )
    )
    if failure == "graph":
        with pytest.raises(TypeError, match="controlled construction error"):
            async with app.router.lifespan_context(app):
                pytest.fail("Graph construction should fail startup")
        assert events == ["store", "embedding", "model", "checkpoint", "database"]
        return
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(2):
                response = await client.get("/health")
                health = response.json()
                assert "private" not in response.text and "postgresql" not in response.text
                assert health["agent_ready"] == (failure not in {"database", "checkpoint"})
                assert health["knowledge_ready"] == (
                    failure not in {"database", "embedding", "knowledge"}
                )
            if failure in {"database", "checkpoint"}:
                response = await client.post(
                    "/agent/chat",
                    json={
                        "user_id": "dev-user",
                        "conversation_id": "controlled",
                        "message": "hello",
                    },
                )
                assert response.status_code == 503
        if app.state.agent_service.is_ready:
            registry = app.state.tool_registry
            assert registry.frozen and registry.get("get_order").metadata.enabled
            assert registry.get("refund_order").metadata.enabled
            assert registry.get("search_knowledge").metadata.enabled == health["knowledge_ready"]
            assert registry.get("write_preferences").metadata.enabled == (failure != "store")
    assert builds.count("model") == 1
    assert builds.count("graph") == (failure not in {"database", "checkpoint"})
    expected = ["store", "embedding", "model", "checkpoint", "database"]
    if failure == "database":
        expected = ["embedding", "model"]
    elif failure == "checkpoint":
        expected.remove("checkpoint")
    elif failure == "store":
        expected.remove("store")
    assert events == expected
