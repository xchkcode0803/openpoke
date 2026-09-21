"""Prepare complete, deduplicated mailbox evidence for semantic judges."""
from dataclasses import asdict

from ..types import Case


def previews(events):
    return [e["arguments"] for e in events if e["kind"] == "interaction_tool"
            and e.get("name") == "send_draft" and e.get("result", {}).get("success")]


def build_judge_state(case: Case, record: dict, index: int) -> dict:
    """Deduplicate read evidence without truncating messages, errors, or mutations."""
    events = [e for e in record["events"] if e["turn"] == index]
    retrieved_ids = {m["id"] for e in record["events"] if e["turn"] <= index and e["kind"] == "gmail_action"
                     and e.get("action") == "GMAIL_FETCH_EMAILS" and not e.get("error")
                     for m in e.get("result", {}).get("data", {}).get("messages", [])}
    actions, reads = [], []
    for sequence, event in enumerate(events):
        if event["kind"] != "gmail_action":
            continue
        before = {m["id"]: m for m in event.get("before", {}).get("messages", [])}
        after = {m["id"]: m for m in event.get("after", {}).get("messages", [])}
        data = event.get("result", {}).get("data", {})
        if event["action"] == "GMAIL_FETCH_EMAILS":
            arguments = event.get("arguments", {})
            reads.append({"sequence": sequence, "query": arguments.get("query"),
                          "max_results": arguments.get("max_results"),
                          "include_spam_trash": arguments.get("include_spam_trash"),
                          "message_ids": [m["id"] for m in data.get("messages", [])],
                          "error": event.get("error")})
            continue
        actions.append({
            "sequence": sequence, "action": event["action"], "arguments": event.get("arguments"),
            "error": event.get("error"), "successful": event.get("result", {}).get("successful"),
            "returned_message_ids": [m["id"] for m in data.get("messages", [])],
            "changed_messages": [m for identifier, m in after.items() if before.get(identifier) != m],
            "removed_message_ids": sorted(before.keys() - after.keys()),
        })
    tool_results = []
    for event in events:
        if event["kind"] != "execution_tool":
            continue
        result = event.get("result", (False, {}))
        payload = result[1] if len(result) > 1 else {}
        tool_results.append({"tool": event.get("name"), "wrapper_success": result[0],
                             "error": payload.get("error") if isinstance(payload, dict) else None})
    return {
        "user_request": case.turns[index].message,
        "previous_user_requests": [t.message for t in case.turns[:index]],
        "previous_previews": previews([e for e in record["events"] if e["turn"] < index]),
        "retrieved_source_emails": [asdict(m) for m in case.mail if m.id in retrieved_ids],
        "visible_outputs": [e["content"] for e in events if e["kind"] == "user_output"],
        "tool_results": tool_results, "actions": actions, "read_results": reads,
        "mailbox": next((t.get("after") for t in record["turns"] if t["index"] == index), None),
    }
