"""Owned resources are closed on normal exit and partial startup failure."""

from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infrastructure.model import model_resources
from app.infrastructure.postgres import DatabaseUnavailableError, open_pool
from app.main import create_app


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
