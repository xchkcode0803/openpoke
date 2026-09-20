"""Deterministic, bounded views of agent names and recorded work."""
import math
import re
import unicodedata
from collections import Counter

MAX_CANDIDATES = 20
RECENT_HISTORY_CHAR_LIMIT = 6000
CURRENT_MESSAGE_WEIGHT = 3
NAME_LENGTH_PENALTY = 0.15
SEARCH_PAGE_SIZE = 10
INSPECTION_PAGE_SIZE = 6
INSPECTION_EXCERPT_CHAR_LIMIT = 1000
OWNERSHIP_EXCERPT_CHAR_LIMIT = 400


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[\W_]+", " ", folded).split())


def _page(items: list, offset: int, size: int) -> dict:
    if type(offset) is not int or not 0 <= offset <= len(items):
        raise ValueError("offset must be an integer between zero and the result count")
    end = min(offset + size, len(items))
    return {"items": items[offset:end], "total_matches": len(items),
            "next_offset": end if end < len(items) else None}


def _terms(normalized_text: str) -> set[str]:
    # Singular/plural variants should not hide an otherwise relevant owner.
    return {word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
            for word in normalized_text.split()}


def rank_names(names: list[str], query: str, history: str = "") -> list[str]:
    """Rank name evidence, giving explicit conversation owners priority.

    Only caller-supplied names and text are used. No task-specific dictionaries,
    expected answers, or model calls are involved.
    """
    normalized_names = {name: normalize(name) for name in names}
    name_terms = {name: _terms(normalized) for name, normalized in normalized_names.items()}
    term_frequencies = Counter(term for terms in name_terms.values() for term in terms)
    normalized_query = normalize(query)
    current_terms = _terms(normalized_query)
    recent_terms = _terms(normalize(history[-RECENT_HISTORY_CHAR_LIMIT:]))
    history_for_mentions = " " + normalize(history) + " "
    query_for_mentions = " " + normalized_query + " "

    priorities = {}
    for name, terms in name_terms.items():
        keyword_score = sum(
            math.log1p(len(names) / term_frequencies[term])
            * (CURRENT_MESSAGE_WEIGHT * (term in current_terms) + (term in recent_terms))
            for term in terms
        )
        # Prefer focused names over long names containing many incidental terms.
        keyword_score /= 1 + NAME_LENGTH_PENALTY * len(terms)
        normalized_name = normalized_names[name]
        last_mention = history_for_mentions.rfind(" " + normalized_name + " ")
        exact_match = normalized_name == normalized_query
        mentioned_now = " " + normalized_name + " " in query_for_mentions
        mentioned_before = last_mention >= 0

        if exact_match or mentioned_now or mentioned_before or keyword_score:
            priorities[name] = (
                exact_match, mentioned_now, mentioned_before, keyword_score, last_mention,
            )

    # Stable sorting keeps alphabetical tie-breaking beneath the routing priorities.
    ranked = sorted(
        (name for name in names if name in priorities),
        key=lambda name: (normalized_names[name], name),
    )
    ranked.sort(key=priorities.__getitem__, reverse=True)
    return ranked


def select_candidates(names: list[str], query: str, history: str, limit: int = MAX_CANDIDATES) -> list[str]:
    if len(names) <= limit:
        return list(names)
    return rank_names(names, query, history)[:limit]


def search_names(names: list[str], query: str, offset: int = 0) -> dict:
    if not isinstance(query, str) or not normalize(query):
        raise ValueError("query must contain at least one word or number")
    page = _page(rank_names(names, query), offset, SEARCH_PAGE_SIZE)
    page["agents"] = page.pop("items")
    return page


def inspect_history(names: list[str], agent_name: str, logs, offset: int = 0) -> dict:
    if not isinstance(agent_name, str) or agent_name not in names:
        raise ValueError("agent_name must exactly match an existing agent")
    entries = [{"type": tag, "timestamp": timestamp, "text": text[:INSPECTION_EXCERPT_CHAR_LIMIT],
                "truncated": len(text) > INSPECTION_EXCERPT_CHAR_LIMIT}
               for tag, timestamp, text in logs.iter_entries(agent_name)
               if tag in {"agent_request", "agent_response"}]
    entries.reverse()
    page = _page(entries, offset, INSPECTION_PAGE_SIZE)
    page["entries"] = page.pop("items")
    page["agent_name"] = agent_name
    return page


def ownership_profile(agent_name: str, logs) -> dict:
    """Small verbatim ownership hints; inspection can retrieve further history."""
    first = last = None
    for tag, _timestamp, text in logs.iter_entries(agent_name):
        if tag == "agent_request":
            if first is None:
                first = text
            last = text
    profile = {"name": agent_name}
    if first is not None:
        profile["initial_assignment"] = first[:OWNERSHIP_EXCERPT_CHAR_LIMIT]
        if last != first:
            profile["latest_assignment"] = last[:OWNERSHIP_EXCERPT_CHAR_LIMIT]
        profile["excerpts_truncated"] = len(first) > OWNERSHIP_EXCERPT_CHAR_LIMIT or len(last) > OWNERSHIP_EXCERPT_CHAR_LIMIT
    return profile
