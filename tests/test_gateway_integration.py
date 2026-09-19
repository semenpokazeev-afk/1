"""
Integration tests for FastAPI Gateway and OpenAI-Compatible API (Module 1)
"""

import pytest
from httpx import AsyncClient, ASGITransport
from arbiter.gateway.app import app


@pytest.mark.asyncio
async def test_get_models():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        model_ids = [m["id"] for m in data["data"]]
        assert "arbiter-auto" in model_ids


@pytest.mark.asyncio
async def test_chat_completions_non_streaming():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "messages": [
                {"role": "user", "content": "напиши простой код на python для вычисления суммы"}
            ]
        }
        headers = {"X-Arbiter-Strategy": "auto"}
        resp = await client.post("/v1/chat/completions", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["choices"][0]["message"]["content"]
        assert data["arbiter_category"] == "code_generation"


@pytest.mark.asyncio
async def test_chat_completions_consensus():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "messages": [
                {"role": "user", "content": "объясни разницу между стеком и очередью"}
            ]
        }
        headers = {"X-Arbiter-Strategy": "consensus"}
        resp = await client.post("/v1/chat/completions", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["arbiter_strategy"] == "consensus"
        assert len(data["choices"][0]["message"]["content"]) > 0


@pytest.mark.asyncio
async def test_feedback_submission():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First make a request to generate an ID
        chat_resp = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]}
        )
        req_id = chat_resp.json()["id"]

        # Submit positive feedback 👍
        fb_resp = await client.post(
            "/v1/arbiter/feedback",
            json={"request_id": req_id, "rating": 1, "comment": "Great routing"}
        )
        assert fb_resp.status_code == 200
        fb_data = fb_resp.json()
        assert fb_data["status"] == "success"
        assert fb_data["alpha_updated"] > 1.0


@pytest.mark.asyncio
async def test_analytics_and_health_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health_resp = await client.get("/v1/arbiter/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert len(health_data) > 0

        summary_resp = await client.get("/v1/arbiter/analytics/summary")
        assert summary_resp.status_code == 200
        summary_data = summary_resp.json()
        assert "forecast" in summary_data
