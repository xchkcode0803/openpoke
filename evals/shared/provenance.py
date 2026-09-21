"""Hash implementation sources without mixing in engineering tests."""
from hashlib import sha256
from pathlib import Path

EVAL_PACKAGES = ("agent_gmail", "agent_overload", "model_comparison", "shared")


def eval_source_hashes(root: Path = Path(".")) -> dict[str, str]:
    paths = [path for package in EVAL_PACKAGES
             for path in (root / "evals" / package).rglob("*.py")
             if not path.name.startswith("test_")]
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}
