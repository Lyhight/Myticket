from httpx import AsyncClient

from app.core.config import settings


async def _admin_token(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "admin-password"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_readiness_and_request_headers(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/health/ready",
        headers={"X-Request-ID": "test-request-id"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": True,
        "rate_limit_backend": "memory",
    }
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert float(response.headers["X-Response-Time-Ms"]) >= 0
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_invalid_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "invalid request id value"},
    )

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert request_id.isalnum()


async def test_prometheus_metrics_are_exposed(client: AsyncClient) -> None:
    await client.get("/api/v1/health")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "myticket_http_requests_total" in response.text
    assert 'route="/api/v1/health"' in response.text


async def test_prometheus_metrics_can_require_bearer_token(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "metrics_bearer_token", "metrics-secret")

    denied = await client.get("/metrics")
    allowed = await client.get(
        "/metrics",
        headers={"Authorization": "Bearer metrics-secret"},
    )

    assert denied.status_code == 401
    assert denied.headers["WWW-Authenticate"] == "Bearer"
    assert allowed.status_code == 200


async def test_admin_can_view_operations(client: AsyncClient, admin_user) -> None:
    token = await _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    metrics = await client.get("/api/v1/operations/metrics", headers=headers)
    assert metrics.status_code == 200
    assert metrics.json()["run_count"] == 0

    alerts = await client.get("/api/v1/operations/alerts", headers=headers)
    assert alerts.status_code == 200
    assert alerts.json()["alerts"] == []
