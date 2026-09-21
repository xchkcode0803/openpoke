from evals.agent_overload.cases.stress import stress_cases, stress_seeds
from evals.agent_overload.runtime.provider import failure_kind


def test_paired_rosters():
    cases = stress_cases()
    assert len(cases) == 24
    assert cases == stress_cases()
    for index, (seed, entity, purposes) in enumerate(stress_seeds()):
        group = cases[index * 3:index * 3 + 3]
        previous = set()
        for size, case in zip((10, 100, 1000), group):
            names = set(case.initial_agents)
            assert len(names) == len(case.initial_agents) == size
            assert previous <= names
            assert case.turns == seed.turns
            assert case.initial_conversation == seed.initial_conversation
            if seed.initial_agents:
                assert case.initial_agents[-len(seed.initial_agents):] == seed.initial_agents
            for name in names - set(seed.initial_agents):
                assert any(name.startswith(f"{entity} {purpose} —") for purpose in purposes) or name.startswith(("Library Card Renewal —", "Bicycle Maintenance —", "Pet Vaccination —", "Garden Supplies —"))
            previous = names


def test_provider_classification():
    assert failure_kind("capacity limit: too many tokens") == "capacity"
    assert failure_kind("OpenRouter request failed (429)") == "provider"
    assert failure_kind("unexpected local exception") == "harness"
    assert failure_kind(None) is None


def test_rate_limit_retries_are_bounded(monkeypatch):
    import asyncio
    import httpx
    from evals.shared import http
    calls = []
    sleeps = []

    class Client:
        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(429, headers={"Retry-After": "7"})

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(http.asyncio, "sleep", sleep)
    response = asyncio.run(http.post_with_retry(Client(), "https://openrouter.ai/api/v1/chat/completions"))
    assert response.status_code == 429
    assert len(calls) == 4
    assert sleeps == [7, 7, 7]
    assert response.extensions["eval_timing"]["attempts"] == 4


def test_retry_after_absent_does_not_add_a_wait(monkeypatch):
    import asyncio
    import httpx
    from evals.shared import http
    calls = []

    class Client:
        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(429)

    async def sleep(*args, **kwargs):
        raise AssertionError("an absent Retry-After must not invent a delay")

    monkeypatch.setattr(http.asyncio, "sleep", sleep)
    response = asyncio.run(http.post_with_retry(Client(), "https://openrouter.ai/api/v1/chat/completions"))
    assert response.status_code == 429
    assert len(calls) == 4


def test_transport_failures_are_not_retried():
    import asyncio
    import httpx
    from evals.shared import http
    calls = []

    class Client:
        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(503)

    response = asyncio.run(http.post_with_retry(Client(), "https://openrouter.ai/api/v1/chat/completions"))
    assert response.status_code == 503
    assert len(calls) == 1


def test_judge_usage_is_recorded_once_per_request(monkeypatch):
    import asyncio
    import httpx
    from evals.shared import judges
    records = []

    async def response(*args, **kwargs):
        return httpx.Response(200, json={"answers": {"a": {"noul": 0.95}, "b": {"noul": 0.95}}, "usage": {"input_tokens": 100, "output_tokens": 5, "cost": 0.01}})

    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test")
    monkeypatch.setattr(judges, "post_with_retry", response)
    monkeypatch.setattr(judges, "save_result", lambda filename, record: records.append(record))
    answers = asyncio.run(judges.OpenRouterJevJudge().evaluate({}, {"a": {}, "b": {}}))
    assert len(answers) == 2
    assert len(records) == 1
    assert records[0]["cost"] == 0.01


def test_artifact_runs_do_not_mix(tmp_path, monkeypatch):
    from evals.agent_overload.runtime import provider
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(provider, "_artifact_dir", None)
    provider.save_result("unavailable.jsonl", {"case": "first"})
    first = provider.artifact_dir()
    monkeypatch.setattr(provider, "_artifact_dir", None)
    provider.save_result("unavailable.jsonl", {"case": "second"})
    second = provider.artifact_dir()
    assert first != second
    assert "second" not in (first / "unavailable.jsonl").read_text()
