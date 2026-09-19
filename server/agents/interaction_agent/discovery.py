"""Deterministic, bounded views of agent names and recorded work."""
import re
import unicodedata


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[\W_]+", " ", folded).split())


def _page(items: list, offset: int, size: int) -> dict:
    if type(offset) is not int or not 0 <= offset <= len(items):
        raise ValueError("offset must be an integer between zero and the result count")
    end = min(offset + size, len(items))
    return {"items": items[offset:end], "total_matches": len(items),
            "next_offset": end if end < len(items) else None}


def search_names(names: list[str], query: str, offset: int = 0) -> dict:
    if not isinstance(query, str) or not normalize(query):
        raise ValueError("query must contain at least one word or number")
    query = normalize(query)
    words = query.split()
    matches = [name for name in names if all(word in normalize(name) for word in words)]
    matches.sort(key=lambda name: (normalize(name) != query, normalize(name), name))
    page = _page(matches, offset, 10)
    page["agents"] = page.pop("items")
    return page


def inspect_history(names: list[str], agent_name: str, logs, offset: int = 0) -> dict:
    if not isinstance(agent_name, str) or agent_name not in names:
        raise ValueError("agent_name must exactly match an existing agent")
    entries = [{"type": tag, "timestamp": timestamp, "text": text[:1000],
                "truncated": len(text) > 1000}
               for tag, timestamp, text in logs.iter_entries(agent_name)
               if tag in {"agent_request", "agent_response"}]
    entries.reverse()
    page = _page(entries, offset, 6)
    page["entries"] = page.pop("items")
    page["agent_name"] = agent_name
    return page
