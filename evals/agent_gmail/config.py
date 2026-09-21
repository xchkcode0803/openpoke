"""Explicit eval-only settings; production defaults are never modified."""
from dataclasses import dataclass

from evals.shared.models import SONNET

DEFAULT_MODEL = SONNET
FIXTURE_VERSION = "3"
GRADER_VERSION = "6"


@dataclass(frozen=True)
class EvalConfig:
    interaction_model: str = DEFAULT_MODEL
    execution_model: str = DEFAULT_MODEL
    search_model: str = DEFAULT_MODEL
    turn_timeout: float = 180
    repetitions: int = 1
    budget: float | None = None
    worker_timeout: float = 90
