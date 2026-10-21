import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.rate_limit import rate_limit


def test_rate_limit_blocks_after_limit_with_memory_fallback():
    app = FastAPI()

    @app.get("/memory")
    async def memory(_limit: None = Depends(rate_limit("test-memory-window", 3, 60))):
        return {"ok": True}

    client = TestClient(app)
    for _ in range(3):
        assert client.get("/memory").status_code == 200
    blocked = client.get("/memory")
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "RATE_LIMITED"


class _CountingRedis:
    def __init__(self):
        self.counts = {}

    async def eval(self, _script, _count, key, window_seconds):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


def test_rate_limit_uses_redis_counter_with_env_key_prefix():
    app = FastAPI()
    redis = _CountingRedis()
    app.state.redis = redis

    @app.get("/redis")
    async def redis_route(_limit: None = Depends(rate_limit("test-redis-window", 2, 60))):
        return {"ok": True}

    settings = get_settings()
    old_prefix = settings.redis_key_prefix
    settings.redis_key_prefix = "staging:"
    try:
        client = TestClient(app)
        assert client.get("/redis").status_code == 200
        assert client.get("/redis").status_code == 200
        assert client.get("/redis").status_code == 429
        assert any(key.startswith("staging:voltstop:rate:test-redis-window:") for key in redis.counts)
    finally:
        settings.redis_key_prefix = old_prefix


class _FailingRedis:
    async def eval(self, *_args):
        raise RedisError("redis down")


def test_rate_limit_fails_open_when_redis_errors():
    app = FastAPI()
    app.state.redis = _FailingRedis()

    @app.get("/fail-open")
    async def fail_open(_limit: None = Depends(rate_limit("test-fail-open-window", 1, 60))):
        return {"ok": True}

    client = TestClient(app)
    for _ in range(3):
        assert client.get("/fail-open").status_code == 200
