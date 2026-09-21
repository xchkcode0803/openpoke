import pytest

from evals.agent_gmail.runtime.adapter import GmailAdapter, UnsupportedOperation
from evals.agent_gmail.runtime.emulator import Emulator
from evals.agent_gmail.cases.mailbox import USER
from evals.agent_gmail.types import Fault, Mail


def test_draft_lifecycle_and_recipients():
    with Emulator() as emulator:
        adapter = GmailAdapter(emulator)
        draft = adapter("GMAIL_CREATE_EMAIL_DRAFT", USER, {
            "recipient_email": "alice@example.com", "subject": "Cedar", "body": "Ready Friday",
            "cc": ["bob@example.com"], "bcc": ["audit@example.com"],
        })["data"]
        mail = emulator.snapshot()["messages"][0]
        assert (mail["body"], mail["cc"], mail["bcc"]) == ("Ready Friday", "bob@example.com", "audit@example.com")
        listed = adapter("GMAIL_LIST_DRAFTS", USER, {"verbose": True})["data"]["drafts"]
        assert listed[0]["id"] == draft["id"]
        adapter("GMAIL_SEND_DRAFT", USER, {"draft_id": draft["id"]})
        assert "SENT" in emulator.snapshot()["messages"][0]["labels"]
        assert adapter("GMAIL_LIST_DRAFTS", USER)["data"]["drafts"] == []
        with pytest.raises(Exception):
            adapter("GMAIL_SEND_DRAFT", USER, {"draft_id": draft["id"]})
        second = adapter("GMAIL_CREATE_EMAIL_DRAFT", USER, {"recipient_email": "a@example.com", "subject": "Delete", "body": "Unused"})["data"]
        adapter("GMAIL_DELETE_DRAFT", USER, {"draft_id": second["id"]})
        assert len(emulator.snapshot()["messages"]) == 1


def test_search_parser_reply_and_forward():
    from server.services.gmail import parse_gmail_fetch_response
    mail = Mail("source", "alice@example.com", USER, "Cedar launch", "Launch Friday at 14:00", "cedar")
    with Emulator((mail,)) as emulator:
        adapter = GmailAdapter(emulator)
        result = adapter("GMAIL_FETCH_EMAILS", USER, {"query": "from:alice@example.com subject:Cedar"})
        parsed, _ = parse_gmail_fetch_response(result, query="Cedar")
        assert parsed[0].clean_text == mail.body
        assert parsed[0].thread_id == "cedar"
        adapter("GMAIL_REPLY_TO_THREAD", USER, {"thread_id": "cedar", "recipient_email": "alice@example.com", "message_body": "Confirmed"})
        adapter("GMAIL_FORWARD_MESSAGE", USER, {"message_id": "source", "recipient_email": "bob@example.com", "additional_text": "Please review"})
        sent = [m for m in emulator.snapshot()["messages"] if "SENT" in m["labels"]]
        assert len(sent) == 2
        assert any(m["thread"] == "cedar" and m["body"] == "Confirmed" for m in sent)
        assert any("Launch Friday at 14:00" in m["body"] and m["to"] == "bob@example.com" for m in sent)


def test_faults_and_unsupported_are_not_successes():
    with Emulator() as emulator:
        adapter = GmailAdapter(emulator, (Fault("GMAIL_CREATE_EMAIL_DRAFT"),))
        args = {"recipient_email": "a@example.com", "subject": "Test", "body": "Hello"}
        with pytest.raises(RuntimeError, match="HTTP 503"):
            adapter("GMAIL_CREATE_EMAIL_DRAFT", USER, args)
        assert emulator.snapshot()["messages"] == []
        adapter("GMAIL_CREATE_EMAIL_DRAFT", USER, args)
        with pytest.raises(UnsupportedOperation):
            adapter("GMAIL_GET_CONTACTS", USER)
        assert adapter.unsupported


def test_html_roundtrip_and_draft_seed():
    seeded = Mail("seed-draft", USER, "bob@example.com", "Unrelated", "Keep me", draft=True)
    with Emulator((seeded,)) as emulator:
        adapter = GmailAdapter(emulator)
        adapter("GMAIL_CREATE_EMAIL_DRAFT", USER, {"recipient_email": "alice@example.com", "subject": "HTML", "body": "<p>Friday &amp; Monday</p>", "is_html": True})
        messages = emulator.snapshot()["messages"]
        assert any(m["body"] == "<p>Friday &amp; Monday</p>" for m in messages)
        from server.services.gmail import parse_gmail_fetch_response
        parsed, _ = parse_gmail_fetch_response(adapter("GMAIL_FETCH_EMAILS", USER, {"query": "subject:HTML"}), query="HTML")
        assert parsed[0].clean_text == "Friday & Monday"
        assert any(m.get("draft_id") and m["subject"] == "Unrelated" for m in messages)
