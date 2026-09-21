"""Pytest/DeepEval entrypoint; the CLI is preferred for complete run manifests."""
import asyncio
import os
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from evals.agent_gmail.cases.definitions import select_cases
from evals.agent_gmail.runtime.config import EvalConfig
from evals.agent_gmail.runtime.harness import run_case
from evals.agent_gmail.grading.metrics import GmailStateMetric, semantic
from evals.agent_gmail.runtime.provider import Provider


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_EVALS") != "1", reason="Paid live evaluation is opt-in")
@pytest.mark.parametrize("case", select_cases(os.getenv("GMAIL_EVAL_SUITE", "smoke")), ids=lambda c: c.name)
def test_live_gmail(case):
    from evals.agent_gmail.run import load_credentials
    load_credentials()
    async def evaluate():
        provider = Provider(EvalConfig())
        await provider.verify()
        record = await run_case(case, provider.config, provider)
        verdict = await semantic(case, record)
        return record, verdict
    record, verdict = asyncio.run(evaluate())
    assert not record.get("unsupported"), "Unsupported adapter capability; inspect coverage"
    assert_test(LLMTestCase(input=case.name, actual_output=str(record["final"]), metadata={"record": record}),
                metrics=[GmailStateMetric(case)], run_async=False)
    assert verdict["passed"], verdict
