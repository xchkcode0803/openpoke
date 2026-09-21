import asyncio

from evals.agent_gmail.runtime.config import EvalConfig
from evals.agent_gmail.runtime.harness import run_case
from evals.agent_gmail.types import Case, Turn


def tool(name, **arguments):
    import json
    if name in {"send_message_to_user", "send_message_to_agent"}:
        arguments.setdefault("end_turn", True)
    return {"id": name, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def response(*calls, content=""):
    return {"choices": [{"message": {"role": "assistant", "content": content, "tool_calls": list(calls)}}]}


def test_real_delegation_worker_callback_and_approval():
    draft = {}
    counts = {"interaction": 0, "execution": 0}
    interaction_prompts = []
    async def scripted(role, messages, **kwargs):
        counts[role] += 1
        if role == "interaction":
            interaction_prompts.append(str(messages))
            text = str(messages)
            if "new_agent_message" in text:
                if len(messages) == 1:
                    if "sent" in text:
                        return response(tool("send_message_to_user", message="Sent."))
                    return response(tool("send_draft", to="alice@example.com", subject="Cedar", body="Friday"),
                                    tool("send_message_to_user", message="Send this draft?"))
                return response()
            if len(messages) == 1:
                instruction = "Send approved draft" if "Yes, send" in text else "Create draft only"
                return response(tool("send_message_to_user", message="Working on it"),
                                tool("send_message_to_agent", agent_name="Cedar mail", action="reuse" if "Send approved" in instruction else "create", instructions=instruction))
            return response(tool("wait", reason="Await worker")) if len(messages) == 4 else response()
        if len(messages) == 1:
            if "Send approved" in str(messages):
                return response(tool("gmail_execute_draft", draft_id=draft["id"]))
            return response(tool("gmail_create_draft", recipient_email="alice@example.com", subject="Cedar", body="Friday"))
        import json
        data = json.loads(messages[-1]["content"])["result"]["data"]
        if "id" not in draft:
            draft["id"] = data["id"]
            return response(content=f"Draft {draft['id']}: To alice@example.com; subject Cedar; body Friday")
        return response(content="Email sent.")
    case = Case("roundtrip", "approval", (Turn("Draft email to Alice"), Turn("Yes, send it", approval=True, requires_preview=True)))
    record = asyncio.run(run_case(case, EvalConfig(), scripted))
    assert len(record["turns"]) == 2
    assert all(t.get("result", {}).get("success") for t in record["turns"])
    assert any(e["kind"] == "callback" for e in record["events"])
    assert any(e["kind"] == "user_output" and "Send this" in e["content"] for e in record["events"])
    assert len([m for m in record["final"]["messages"] if "SENT" in m["labels"]]) == 1
    assert counts["execution"] == 4
    assert any("Create draft only" in prompt for prompt in interaction_prompts)


def test_missing_preview_does_not_invent_approval_state():
    async def scripted(**kwargs):
        return response(content="Unable to create a draft")
    case = Case("missing", "approval", (Turn("Draft an email"), Turn("Send it", approval=True, requires_preview=True)))
    record = asyncio.run(run_case(case, EvalConfig(), scripted))
    assert record["turns"][1]["failure_kind"] == "dependency"
    assert record["final"]["messages"] == []


def test_timeout_cancels_worker_and_restores_event_loop():
    async def check():
        loop = asyncio.get_running_loop()
        original = loop.create_task
        async def slow(**kwargs):
            await asyncio.sleep(10)
        record = await run_case(Case("timeout", "errors", (Turn("Draft"),)), EvalConfig(turn_timeout=0.02), slow)
        assert record["turns"][0]["failure_kind"] == "agent_timeout"
        assert loop.create_task == original
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    asyncio.run(check())


def test_actual_nested_search_loop_and_callback():
    from evals.agent_gmail.types import Mail
    from evals.agent_gmail.cases.mailbox import USER
    from server.agents.execution_agent.tasks.search_email.schemas import TASK_TOOL_NAME, SEARCH_TOOL_NAME, COMPLETE_TOOL_NAME
    async def scripted(role, messages, **kwargs):
        if role == "interaction":
            if len(messages) > 1:
                return response()
            if "new_agent_message" in str(messages):
                return response(tool("send_message_to_user", message="Reference CEDAR-42"))
            return response(tool("send_message_to_user", message="Searching"), tool("send_message_to_agent", agent_name="Cedar", action="create", instructions="Find reference"))
        if role == "execution":
            if len(messages) == 1:
                return response(tool(TASK_TOOL_NAME, search_query="from:alice@example.com"))
            return response(content="Reference CEDAR-42")
        if len(messages) == 1:
            return response(tool(SEARCH_TOOL_NAME, query="from:alice@example.com"))
        return response(tool(COMPLETE_TOOL_NAME, message_ids=["source"]))
    case = Case("nested", "search", (Turn("Find reference"),), (Mail("source", "alice@example.com", USER, "Cedar", "CEDAR-42"),))
    record = asyncio.run(run_case(case, EvalConfig(), scripted))
    assert {e["role"] for e in record["events"] if e["kind"] == "model"} == {"interaction", "execution", "search"}
    assert any(e["kind"] == "gmail_action" and e["action"] == "GMAIL_FETCH_EMAILS" for e in record["events"])
    assert "CEDAR-42" in record["turns"][0]["conversation"]
