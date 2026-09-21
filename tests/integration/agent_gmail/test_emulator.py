from evals.agent_gmail.runtime.emulator import Emulator
from evals.agent_gmail.cases.mailbox import USER
from evals.agent_gmail.types import Mail


def test_seed_readback_and_fresh_mailbox():
    mail = Mail("seed-one", "alice@example.com", USER, "Project Cedar", "Launch Friday", "cedar")
    with Emulator((mail,)) as emulator:
        messages = emulator.snapshot()["messages"]
        target = next(m for m in messages if m["id"] == mail.id)
        assert target["subject"] == mail.subject
        assert target["body"] == mail.body
        assert target["thread"] == mail.thread
    with Emulator() as emulator:
        assert emulator.snapshot()["messages"] == []


def test_startup_readiness_repeated():
    for _ in range(3):
        with Emulator() as emulator:
            assert emulator.snapshot()["messages"] == []
