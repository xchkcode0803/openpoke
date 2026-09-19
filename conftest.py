"""Isolate service imports before collection, including repository-root runs."""
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch


def pytest_sessionstart(session):
    directory = TemporaryDirectory(prefix="openpoke-eval-session-")
    environment = patch.dict(os.environ, {"OPENPOKE_DATA_DIR": directory.name})
    environment.start()
    session._overload_isolation = (directory, environment)
    session.config.add_cleanup(lambda: _cleanup_isolation(session))


def pytest_sessionfinish(session, exitstatus):
    _cleanup_isolation(session)


def _cleanup_isolation(session):
    isolation = getattr(session, "_overload_isolation", None)
    if isolation:
        directory, environment = isolation
        session._overload_isolation = None
        environment.stop()
        directory.cleanup()
