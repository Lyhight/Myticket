from httpx import AsyncClient


async def login(
    client: AsyncClient,
    *,
    email: str,
    password: str,
) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_admin_can_manage_and_search_knowledge(
    client: AsyncClient,
    admin_user,
) -> None:
    token = await login(
        client,
        email="admin@example.com",
        password="admin-password",
    )

    create_response = await client.post(
        "/api/v1/knowledge",
        headers=headers(token),
        json={
            "title": "会员积分规则",
            "source": "manual://points-policy",
            "content": "订单完成后会获得会员积分，退款后积分会扣回。",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    document_id = created["document"]["id"]
    assert created["chunk_count"] == 1
    assert created["document"]["is_active"] is True

    list_response = await client.get(
        "/api/v1/knowledge",
        headers=headers(token),
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    search_response = await client.post(
        "/api/v1/knowledge/search",
        headers=headers(token),
        json={"query": "退款以后积分怎么办", "top_k": 3},
    )
    assert search_response.status_code == 200
    assert search_response.json()[0]["source"] == (
        "manual://points-policy"
    )

    update_response = await client.put(
        f"/api/v1/knowledge/{document_id}",
        headers=headers(token),
        json={
            "title": "会员等级规则",
            "content": "会员等级根据成长值计算，每月更新一次。",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["document"]["title"] == (
        "会员等级规则"
    )

    old_search = await client.post(
        "/api/v1/knowledge/search",
        headers=headers(token),
        json={"query": "退款积分", "top_k": 3},
    )
    assert old_search.status_code == 200
    assert old_search.json() == []

    delete_response = await client.delete(
        f"/api/v1/knowledge/{document_id}",
        headers=headers(token),
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False

    inactive_search = await client.post(
        "/api/v1/knowledge/search",
        headers=headers(token),
        json={"query": "会员等级成长值", "top_k": 3},
    )
    assert inactive_search.status_code == 200
    assert inactive_search.json() == []


async def test_customer_cannot_manage_knowledge(
    client: AsyncClient,
) -> None:
    await client.post(
        "/api/v1/users",
        json={
            "email": "customer@example.com",
            "password": "strong-password",
        },
    )
    token = await login(
        client,
        email="customer@example.com",
        password="strong-password",
    )

    response = await client.post(
        "/api/v1/knowledge",
        headers=headers(token),
        json={
            "title": "无权文档",
            "source": "manual://forbidden",
            "content": "普通用户不能创建知识文档。",
        },
    )

    assert response.status_code == 403


async def test_updating_missing_document_returns_404(
    client: AsyncClient,
    admin_user,
) -> None:
    token = await login(
        client,
        email="admin@example.com",
        password="admin-password",
    )

    response = await client.put(
        "/api/v1/knowledge/9999",
        headers=headers(token),
        json={"title": "不存在", "content": "不存在的文档"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Knowledge document not found"
