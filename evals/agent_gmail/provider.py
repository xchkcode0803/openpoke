"""Live model transport with verified IDs and usage records."""
import asyncio
import os
import time
import httpx
from evals.shared.http import post_with_retry
from evals.shared.usage import effective_cost


class ProviderFailure(RuntimeError):
    pass


class Provider:
    def __init__(self, config):
        self.config = config
        self.calls = []
        self.metadata = []
        self.known_cost = 0.0
        self.cost_unknown = False

    async def verify(self):
        if not os.getenv("OPENROUTER_API_KEY"):
            raise ProviderFailure("OPENROUTER_API_KEY is required")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            catalog = {m["id"]: m for m in response.json()["data"]}
        for model in sorted({self.config.interaction_model, self.config.execution_model, self.config.search_model}):
            if model not in catalog or "tools" not in catalog[model].get("supported_parameters", []):
                raise ProviderFailure(f"Requested model missing or lacks tools: {model}")
            self.metadata.append(catalog[model])

    async def __call__(self, *, role, model, messages, system=None, tools=None, **kwargs):
        payload = {"model": model, "messages": ([{"role": "system", "content": system}] if system else []) + messages, "stream": False}
        if tools:
            payload["tools"] = tools
        call = {"role": role, "model": model, "attempts": []}
        self.calls.append(call)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await post_with_retry(
                    client,
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
                    json=payload,
                )
                call["attempts"].append({"status": response.status_code, **response.extensions["eval_timing"]})
            if response.is_error:
                raise ProviderFailure(f"OpenRouter HTTP {response.status_code}: {response.text[:1000]}")
            result = response.json()
            if result.get("error") or not result.get("choices"):
                raise ProviderFailure(f"Invalid model response: {result}")
            usage = result.get("usage", {})
            cost = effective_cost(usage)
            self.cost_unknown |= not isinstance(cost, (int, float))
            if isinstance(cost, (int, float)):
                self.known_cost += cost
            call.update(usage=usage, provider=result.get("provider"), returned_model=result.get("model"), generation_id=result.get("id"))
            return result
        except asyncio.CancelledError:
            self.cost_unknown = True
            call["cancelled"] = True
            raise
        except Exception as exc:
            self.cost_unknown = True
            call["error"] = str(exc)
            raise
        finally:
            call["seconds"] = time.perf_counter() - started
