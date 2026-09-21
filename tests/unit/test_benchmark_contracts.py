"""Frozen behavior contracts captured before the eval organization cleanup."""
from dataclasses import asdict
from hashlib import sha256
import json

from evals.agent_gmail.cases import select_cases
from evals.agent_gmail.metrics import CONTENT_CRITERION, REPORTING_CRITERION
from evals.agent_overload.cases import full_cases
from evals.agent_overload.inspection_cases import INSPECTION_CASES, INSPECTION_HISTORY
from evals.agent_overload.routing_population import SCALE_VARIANTS, CHALLENGE_VARIANTS
from evals.agent_overload.stress_cases import stress_cases


EXPECTED = {
    "challenge": "b9795ffb6f78b7ad199fd156fa139a6fb75abb45dfc16c3846211bfc92ec62f2",
    "content": "d8980c1403923a0357c870f2d291a9c68d880e62ae4d0d762de17fb6171fd35b",
    "gmail": "405899d52a180dc4832ddd97ced71e70171ae371fe5f7096d7cd2bcc7095f0e2",
    "history": "70fd5eb9e4f15e9414c6c332fefc28682b1e34e88532228ecd23a69cb1e0fd76",
    "inspection": "3a8a387b9f49def506cd196b799bf4d46bdaf316f85e7b7b276cb1612c91c68f",
    "reporting": "3ebf702b3ca393c9849429f94fd026dfa9ad2e92087132d99cfe5f1bdcd88ea3",
    "routing": "deca7fed87c6fec8fed3d72518cd4e9dbacb1d03ba64463d1dac5a7e206f1ddd",
    "scale": "e95a54043acb33825a92915a37ca6bbaf8c89a13cd407298699f35b7fb75f6f2"
}


def test_benchmark_contracts_survive_reorganization():
    fixtures = {
        "gmail": select_cases("full"),
        "routing": full_cases() + stress_cases(),
        "inspection": INSPECTION_CASES,
        "scale": SCALE_VARIANTS,
        "challenge": CHALLENGE_VARIANTS,
    }
    contracts = {name: [asdict(case) for case in cases] for name, cases in fixtures.items()}
    contracts.update(history=INSPECTION_HISTORY, content=CONTENT_CRITERION,
                     reporting=REPORTING_CRITERION)
    actual = {
        name: sha256(json.dumps(value, sort_keys=True, default=sorted).encode()).hexdigest()
        for name, value in contracts.items()
    }
    assert actual == EXPECTED
