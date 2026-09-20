"""Deterministic, bounded views of agent names and recorded work."""
import re
import math
from collections import Counter
import unicodedata

MAX_CANDIDATES = 20


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[\W_]+", " ", folded).split())


def _page(items: list, offset: int, size: int) -> dict:
    if type(offset) is not int or not 0 <= offset <= len(items):
        raise ValueError("offset must be an integer between zero and the result count")
    end = min(offset + size, len(items))
    return {"items": items[offset:end], "total_matches": len(items),
            "next_offset": end if end < len(items) else None}


def _terms(text: str) -> set[str]:
    # Singular/plural variants should not hide an otherwise relevant owner.
    return {word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
            for word in normalize(text).split()}


def rank_names(names: list[str], query: str, history: str = "") -> list[str]:
    """Rank name evidence, giving explicit conversation owners priority.

    Only caller-supplied names and text are used. No task-specific dictionaries,
    expected answers, or model calls are involved.
    """
    documents = {name: _terms(name) for name in names}
    frequencies = Counter(term for terms in documents.values() for term in terms)
    current = _terms(query)
    context = _terms(history[-6000:])
    normalized_context = " " + normalize(history) + " "
    exact = normalize(query)
    normalized_query = " " + exact + " "

    def score(name: str) -> tuple:
        terms = documents[name]
        weight = sum(math.log1p(len(names) / frequencies[term]) *
                     (3 * (term in current) + (term in context)) for term in terms)
        # Prefer focused names over long names containing many incidental terms.
        weight /= 1 + 0.15 * len(terms)
        mention = normalized_context.rfind(" " + normalize(name) + " ")
        return (normalize(name) == exact, " " + normalize(name) + " " in normalized_query,
                mention >= 0, weight, mention)

    ranked = sorted(names, key=lambda name: (normalize(name), name))
    ranked.sort(key=score, reverse=True)
    return [name for name in ranked if any(score(name)[i] for i in (0, 1, 2, 3))]


def select_candidates(names: list[str], query: str, history: str, limit: int = MAX_CANDIDATES) -> list[str]:
    if len(names) <= limit:
        return list(names)
    return rank_names(names, query, history)[:limit]


def search_names(names: list[str], query: str, offset: int = 0) -> dict:
    if not isinstance(query, str) or not normalize(query):
        raise ValueError("query must contain at least one word or number")
    page = _page(rank_names(names, query), offset, 10)
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


def ownership_profile(agent_name: str, logs) -> dict:
    """Small verbatim ownership hints; inspection can retrieve further history."""
    first = last = None
    for tag, timestamp, text in logs.iter_entries(agent_name):
        if tag == "agent_request":
            if first is None:
                first = text
            last = text
    profile = {"name": agent_name}
    if first is not None:
        profile["initial_assignment"] = first[:400]
        if last != first:
            profile["latest_assignment"] = last[:400]
        profile["excerpts_truncated"] = len(first) > 400 or len(last) > 400
    return profile
