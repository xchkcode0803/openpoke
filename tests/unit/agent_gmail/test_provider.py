import asyncio
import httpx
import pytest
from evals.agent_gmail.config import EvalConfig, DEFAULT_MODEL
from evals.agent_gmail.provider import Provider, ProviderFailure


def test_model_catalog_missing_tools_never_substitutes(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    async def get(self, url):
        return httpx.Response(200, request=httpx.Request("GET", url), json={"data": [{"id": DEFAULT_MODEL, "supported_parameters": []}]})
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    with pytest.raises(ProviderFailure, match="lacks tools"):
        asyncio.run(Provider(EvalConfig()).verify())


def test_transport_retains_usage_without_recording_credentials(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    async def post(self, url, headers, json):
        assert headers["Authorization"] == "Bearer test-secret"
        assert json["model"] == DEFAULT_MODEL
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}],
                                        "usage": {"cost": 0, "is_byok": True, "cost_details": {"upstream_inference_cost": .2}}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    provider = Provider(EvalConfig())
    asyncio.run(provider(role="execution", model=DEFAULT_MODEL, messages=[]))
    assert provider.known_cost == .2
    assert "test-secret" not in str(provider.calls)


def test_cancelled_request_marks_usage_unknown(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError()
    monkeypatch.setattr(httpx.AsyncClient, "post", cancelled)
    provider = Provider(EvalConfig())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(provider(role="execution", model=DEFAULT_MODEL, messages=[]))
    assert provider.calls[0]["cancelled"]
    assert provider.cost_unknown is True
