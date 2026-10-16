from httpx import AsyncClient

from app.core.config import settings


async def create_user(
    client: AsyncClient,
    *,
    email: str = "customer@example.com",
    password: str = "strong-password",
):
    return await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": password,
        },
    )


async def login(
    client: AsyncClient,
    *,
    email: str = "customer@example.com",
    password: str = "strong-password",
):
    return await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


async def test_create_user(client: AsyncClient) -> None:
    response = await create_user(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "customer@example.com"
    assert body["role"] == "customer"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


async def test_registration_rejects_weak_password(client: AsyncClient) -> None:
    response = await create_user(client, password="short")

    assert response.status_code == 422


async def test_duplicate_email_is_rejected(
    client: AsyncClient,
) -> None:
    first_response = await create_user(client)
    second_response = await create_user(client)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Email already registered"
    )


async def test_login_and_get_current_user(
    client: AsyncClient,
) -> None:
    await create_user(client)
    login_response = await login(client)

    assert login_response.status_code == 200
    token_body = login_response.json()
    assert token_body["token_type"] == "bearer"
    assert token_body["access_token"]

    me_response = await client.get(
        "/api/v1/users/me",
        headers={
            "Authorization": (
                f"Bearer {token_body['access_token']}"
            ),
        },
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "customer@example.com"


async def test_browser_session_uses_http_only_cookie(
    client: AsyncClient,
) -> None:
    await create_user(client)

    login_response = await login(client)

    cookie = login_response.headers["set-cookie"]
    assert "myticket_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/api" in cookie

    me_response = await client.get("/api/v1/users/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "customer@example.com"


async def test_https_mode_marks_session_cookie_secure(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    await create_user(client)

    login_response = await login(client)

    assert " Secure" in login_response.headers["set-cookie"]


async def test_logout_clears_browser_session_cookie(
    client: AsyncClient,
) -> None:
    await create_user(client)
    await login(client)

    logout_response = await client.post("/api/v1/auth/logout")

    assert logout_response.status_code == 204
    assert "Max-Age=0" in logout_response.headers["set-cookie"]
    me_response = await client.get("/api/v1/users/me")
    assert me_response.status_code == 401


async def test_invalid_password_is_rejected(
    client: AsyncClient,
) -> None:
    await create_user(client)
    response = await login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid email or password"
    )


async def test_unknown_user_is_rejected(
    client: AsyncClient,
) -> None:
    response = await login(
        client,
        email="missing@example.com",
    )
    assert response.status_code == 401


async def test_repeated_login_attempts_are_rate_limited(
    client: AsyncClient,
) -> None:
    for _ in range(10):
        response = await login(client, email="limited@example.com")
        assert response.status_code == 401

    blocked = await login(client, email="limited@example.com")

    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]


async def test_protected_endpoint_requires_token(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code in {401, 403}


async def test_invalid_token_is_rejected(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/users/me",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"
