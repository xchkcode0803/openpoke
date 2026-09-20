"""Live model transport with verified IDs, bounded retries, and usage records."""
import asyncio
import os
import time
import httpx
from .usage import effective_cost


class ProviderFailure(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class Provider:
    def __init__(self, config, transport=None):
        self.config = config
        self.transport = transport
        self.calls = []
        self.metadata = []
        self.known_cost = 0.0
        self.cost_unknown = False
        self.judge_cost = 0.0
        self.judge_cost_unknown = False
        self.budget_stopped = False

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

    def check_budget(self):
        if self.config.budget is not None and (self.known_cost + self.judge_cost >= self.config.budget or self.cost_unknown or self.judge_cost_unknown):
            self.budget_stopped = True
            raise BudgetExceeded("Spending cap reached or usage cost unavailable; no new model calls")
    async def __call__(self, *, role, model, messages, system=None, tools=None, **kwargs):
        self.check_budget()
        payload = {"model": model, "messages": ([{"role": "system", "content": system}] if system else []) + messages, "stream": False}
        if tools:
            payload["tools"] = tools
        call = {"role": role, "model": model, "attempts": []}
        self.calls.append(call)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                for attempt in range(1 if self.transport else 4):
                    async def post(url, **options):
                        if self.transport:
                            return await self.transport(client, url, **options)
                        return await client.post(url, **options)
                    response = await post("https://openrouter.ai/api/v1/chat/completions",
                                                 headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}, json=payload)
                    call["attempts"].append({"status": response.status_code, **response.extensions.get("eval_timing", {})})
                    if self.transport or response.status_code != 429 or attempt == 3:
                        break
                    delay = response.headers.get("Retry-After", "")
                    await asyncio.sleep(min(float(delay) if delay.isdigit() else 2 ** attempt, 30))
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
