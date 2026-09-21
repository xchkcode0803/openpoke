"""Explicitly invoked paid routing evaluations."""

from __future__ import annotations

import os

import pytest
from evals.agent_overload.cases import (
    full_cases,
    smoke_cases,
    standard_cases,
)
from evals.agent_overload.harness import evaluate_live_case
from evals.agent_overload.stress_cases import stress_cases


def suite_parameters():
    full = {case.name for case in full_cases() + stress_cases()}
    smoke = {case.name for case in smoke_cases()}
    standard = {case.name for case in standard_cases()}
    cases = {case.name: case for case in full_cases() + stress_cases() + smoke_cases() + standard_cases()}
    return [
        pytest.param(case, id=case.name, marks=[
            getattr(pytest.mark, suite) for suite, included in (
                ("full", case.name in full), ("smoke", case.name in smoke),
                ("standard", case.name in standard), ("stress", "stress" in case.tags)
            ) if included
        ])
        for case in cases.values()
    ]


@pytest.mark.live
@pytest.mark.parametrize("case", suite_parameters())
def test_live_routing(case) -> None:
    if not os.getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call the interaction model")
    evaluate_live_case(case)
