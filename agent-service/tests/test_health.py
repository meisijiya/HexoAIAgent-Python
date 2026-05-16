"""Smoke test: 健康检查接口"""
import pytest

@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    """Smoke test: 健康检查接口"""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
