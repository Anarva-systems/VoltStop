import httpx
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.main import app

client = TestClient(app)


def test_root_returns_minimal_status_response() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "healthy"},
        "message": "VoltStop API process is responding",
    }


def test_health_returns_standard_envelope() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "healthy"},
        "message": "API liveness check passed",
    }


class _Connection:
    def __init__(self, push_tables: bool = False) -> None:
        self.push_tables = push_tables

    async def fetchval(self, query: str) -> int | bool | None:
        if query == "SELECT 1":
            return 1
        if "to_regclass('public.platform_commission_settings')" in query:
            return False
        if "to_regclass('public.payment_commission_ledger')" in query:
            return False
        if "to_regclass('public.vendor_payout_transfers')" in query:
            return False
        if "to_regclass('public.push_deliveries')" in query:
            return self.push_tables
        if "to_regclass('public.user_push_tokens')" in query:
            return self.push_tables
        if "information_schema.triggers" in query:
            return False
        if "information_schema.columns" in query:
            return False
        raise AssertionError(f"Unexpected readiness query: {query}")


class _Acquire:
    def __init__(self, push_tables: bool = False) -> None:
        self.push_tables = push_tables

    async def __aenter__(self) -> _Connection:
        return _Connection(self.push_tables)

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Pool:
    def __init__(self, push_tables: bool = False) -> None:
        self.push_tables = push_tables

    def acquire(self) -> _Acquire:
        return _Acquire(self.push_tables)


class _Redis:
    async def ping(self) -> bool:
        return True


def _patch_readiness_dependencies(monkeypatch, main_module, auth_response, *,
                                  push_tables: bool = False,
                                  fcm_service_account_json: str = ""):
    async def get_db_pool(_request):
        return _Pool(push_tables)

    async def get_http_client(_request):
        class _HttpClient:
            async def get(self, *_args, **_kwargs):
                if isinstance(auth_response, Exception):
                    raise auth_response
                return auth_response

        return _HttpClient()

    async def get_redis(_request):
        return _Redis()

    monkeypatch.setattr(main_module, "get_db_pool", get_db_pool)
    monkeypatch.setattr(main_module, "get_http_client", get_http_client)
    monkeypatch.setattr(main_module, "get_redis", get_redis)
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            supabase_url="https://project.supabase.co",
            supabase_api_key="public-key-fixture",
            razorpay_key_id="",
            razorpay_key_secret="",
            razorpay_webhook_secret="",
            razorpay_mode="",
            vendor_settlement_enabled=False,
            fcm_project_id="voltstop-app",
            fcm_service_account_json=fcm_service_account_json,
        ),
    )


def test_ready_checks_database_supabase_auth_and_redis(monkeypatch) -> None:
    import app.main as main_module

    _patch_readiness_dependencies(
        monkeypatch,
        main_module,
        httpx.Response(200, json={"version": "test"}),
    )

    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["data"]["dependencies"] == {
        "database": "reachable",
        "supabase_auth": "reachable",
        "redis": "reachable",
    }
    assert "public-key-fixture" not in response.text


def test_ready_reports_supabase_transport_failure_without_secrets(monkeypatch) -> None:
    import app.main as main_module

    request = httpx.Request("GET", "https://project.supabase.co/auth/v1/health")
    _patch_readiness_dependencies(
        monkeypatch,
        main_module,
        httpx.ConnectError("connection refused", request=request),
    )

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json()["data"]["dependencies"] == {
        "database": "reachable",
        "supabase_auth": "network_error",
        "redis": "reachable",
    }
    assert "connection refused" not in response.text
    assert "public-key-fixture" not in response.text


def test_ready_flags_push_dispatch_without_its_tables(monkeypatch) -> None:
    import app.main as main_module

    _patch_readiness_dependencies(
        monkeypatch,
        main_module,
        httpx.Response(200, json={"version": "test"}),
        fcm_service_account_json='{"project_id":"voltstop-app"}',
    )

    response = client.get("/api/v1/ready")

    assert response.json()["data"]["capabilities"]["push_notifications"] == "migration_required"


def test_ready_reports_push_dispatch_configured(monkeypatch) -> None:
    import app.main as main_module

    _patch_readiness_dependencies(
        monkeypatch,
        main_module,
        httpx.Response(200, json={"version": "test"}),
        push_tables=True,
        fcm_service_account_json='{"project_id":"voltstop-app"}',
    )

    response = client.get("/api/v1/ready")

    assert response.json()["data"]["capabilities"]["push_notifications"] == "configured"


def test_ready_keeps_push_unconfigured_by_default(monkeypatch) -> None:
    import app.main as main_module

    _patch_readiness_dependencies(
        monkeypatch,
        main_module,
        httpx.Response(200, json={"version": "test"}),
    )

    response = client.get("/api/v1/ready")

    assert response.json()["data"]["capabilities"]["push_notifications"] == "not_configured"
