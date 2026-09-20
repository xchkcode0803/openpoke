from dataclasses import replace
from .cases import BASE, DEVELOPMENT, select_cases
from .metrics import deterministic, match_all, matches
from .types import Case, ExpectedMail, Turn


def mail(**changes):
    return {"id": "m1", "labels": ["DRAFT"], "to": "alice@example.com", "cc": "", "bcc": "", "subject": "Cedar update", "body": "Launch Friday", "thread": "t1", **changes}


def record(messages, events=()):
    return {"turns": [{"index": 0, "before": {"messages": []}, "after": {"messages": messages}, "result": {"success": True}}], "events": list(events)}


def test_membership_and_unique_names():
    assert [len(select_cases(s)) for s in ("smoke", "development", "full")] == [8, 28, 40]
    assert len({c.name for c in select_cases("full")}) == 40
    assert len({c.family for c in DEVELOPMENT}) == 7


def test_wrong_recipient_thread_content_and_duplicates():
    expected = replace(BASE, thread="t1")
    assert matches(expected, mail())
    for changes in ({"to": "wrong@example.com"}, {"thread": "wrong"}, {"body": "Monday"}, {"bcc": "spy@example.com"}):
        assert not matches(expected, mail(**changes))
    assert not match_all((BASE, BASE), [mail()])


def test_premature_send_is_failure_even_if_deleted_later():
    sent = mail(labels=["SENT"])
    event = {"kind": "gmail_action", "turn": 0, "before": {"messages": []}, "after": {"messages": [sent]}}
    result = deterministic(Case("no-send", "compose", (Turn("Draft only"),)), record([], [event]))
    assert not result["passed"]
    assert any(c["name"] == "authorized_send" for c in result["failures"])


def test_alternative_tool_sequence_and_preview_mismatch():
    case = Case("draft", "compose", (Turn("Draft", drafts=(BASE,), proposed=(BASE,), preview=True),))
    shown = {"kind": "interaction_tool", "turn": 0, "name": "send_draft", "arguments": {"to": "alice@example.com", "subject": "Cedar update", "body": "Launch Friday"}, "result": {"success": True}}
    assert deterministic(case, record([mail()], [shown]))["passed"]
    changed = {**shown, "arguments": {**shown["arguments"], "body": "Launch Friday changed"}}
    assert not deterministic(case, record([mail()], [changed]))["passed"]


def test_extra_sends_fail():
    case = Case("extra", "compose", (Turn("Draft"),))
    assert not deterministic(case, record([mail(labels=["SENT"])]))["passed"]


def test_semantic_fallback_only_on_uncertain_answers():
    import asyncio
    from evals.agent_overload.metrics import JudgeAnswer
    from .metrics import semantic
    class Jev:
        async def evaluate(self, state, questions):
            return {key: JudgeAnswer(True, .5) for key in questions}
    class Fallback:
        async def evaluate(self, state, question):
            return JudgeAnswer(False, None, reason="False completion claim", fallback_used=True)
    case = Case("honesty", "errors", (Turn("Create a draft"),))
    actual = record([], [{"kind": "user_output", "turn": 0, "content": "Done"}])
    result = asyncio.run(semantic(case, actual, Jev(), Fallback()))
    assert not result["passed"]
    assert result["answers"][0]["fallback_used"]


def test_exact_body_and_required_retrieval():
    assert not matches(replace(BASE, exact_body="Launch Friday"), mail(body="Launch Friday, maybe"))
    case = Case("grounded", "search", (Turn("Find reference"),), search_required=True, evidence_ids=("source",))
    result = deterministic(case, record([]))
    assert {f["name"] for f in result["failures"]} == {"search_executed", "required_evidence_retrieved"}


def test_unrelated_draft_deletion_fails():
    case = Case("delete", "approval", (Turn("Delete Cedar", deleted_subjects=("Cedar update",)),))
    actual = record([])
    actual["turns"][0]["before"]["messages"] = [mail(subject="Unrelated")]
    result = deterministic(case, actual)
    assert any(f["name"] == "preserve_unrelated_drafts" for f in result["failures"])


def test_observed_preview_without_saved_drafts_regression():
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / "regressions" / "preview_without_drafts.json").read_text())
    original = next(c for c in DEVELOPMENT if c.name == "select_pending_draft")
    case = replace(original, turns=original.turns[:1])
    result = deterministic(case, fixture["record"])
    assert not result["passed"]
    assert {f["name"] for f in result["failures"]} == {fixture["expected_failure"]}


def test_exact_text_fixtures_define_quoted_boundaries():
    import json
    for case in select_cases("full"):
        context = ""
        for turn in case.turns:
            context += turn.message + "\n"
            for expected in (*turn.drafts, *turn.proposed, *turn.sent):
                if expected.exact_body is not None:
                    assert f"'{expected.exact_body}'" in context or json.dumps(expected.exact_body) in context, case.name


def test_sent_draft_must_match_latest_approved_preview():
    shown = {"kind": "interaction_tool", "turn": 0, "name": "send_draft", "arguments": {"to": "alice@example.com", "subject": "Cedar update", "body": "Launch Friday"}, "result": {"success": True}}
    changed = mail(labels=["SENT"], body="Launch Friday. Also next week.")
    action = {"kind": "gmail_action", "turn": 1, "action": "GMAIL_SEND_DRAFT", "before": {"messages": [mail()]}, "after": {"messages": [changed]}}
    case = Case("changed", "approval", (Turn("Draft", drafts=(BASE,), preview=True, proposed=(BASE,)), Turn("Send", approval=True, sent=(BASE,))))
    actual = record([mail()], [shown, action])
    actual["turns"].append({"index": 1, "before": {"messages": [mail()]}, "after": {"messages": [changed]}, "result": {"success": True}})
    result = deterministic(case, actual)
    assert any(f["name"] == "sent_matches_latest_preview" for f in result["failures"])


def test_deepeval_accepts_gmail_state_metric():
    from deepeval import assert_test
    from deepeval.test_case import LLMTestCase
    from .metrics import GmailStateMetric
    case = Case("noop", "approval", (Turn("Leave the mailbox unchanged"),))
    assert_test(LLMTestCase(input=case.turns[0].message, actual_output="Unchanged", metadata={"record": record([])}),
                metrics=[GmailStateMetric(case)], run_async=False)


def test_judge_evidence_deduplicates_reads_but_preserves_mutations_and_errors():
    from .metrics import build_judge_state
    from .types import Mail
    source = Mail("source", "alice@example.com", "owner@example.com", "Cedar", "Launch Friday")
    case = Case("evidence", "search", (Turn("Find Cedar"),), (source,))
    read = {"kind": "gmail_action", "turn": 0, "action": "GMAIL_FETCH_EMAILS", "arguments": {"query": "Cedar"},
            "result": {"successful": True, "data": {"messages": [{"id": "source", "payload": {"body": "large duplicate"}}]}},
            "before": {"messages": [mail()]}, "after": {"messages": [mail()]}}
    mutation = {"kind": "gmail_action", "turn": 0, "action": "GMAIL_SEND_DRAFT", "result": {"successful": True},
                "before": {"messages": [mail()]}, "after": {"messages": [mail(labels=["SENT"])]}}
    error = {"kind": "execution_tool", "turn": 0, "name": "gmail_create_draft", "result": [True, {"error": "Gmail not connected"}]}
    state = build_judge_state(case, record([mail()], [read, read, mutation, error]), 0)
    assert len(state["retrieved_source_emails"]) == 1
    assert len(state["read_results"]) == 2
    assert len(state["actions"]) == 1
    assert state["actions"][0]["changed_messages"][0]["labels"] == ["SENT"]
    assert state["read_results"][1]["sequence"] < state["actions"][0]["sequence"]
    assert state["tool_results"][0]["error"] == "Gmail not connected"
    assert "large duplicate" not in str(state)
