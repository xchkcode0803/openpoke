"""Lossless eval events with causal span IDs; never stores authentication headers."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import time
from uuid import uuid4

parent_span = ContextVar("gmail_eval_span", default=None)


class Recorder:
    def __init__(self):
        self.events = []
        self.turn = -1

    def emit(self, kind, **data):
        event = {"id": uuid4().hex, "parent": parent_span.get(), "turn": self.turn,
                 "kind": kind, "time": time.time(), **deepcopy(data)}
        self.events.append(event)
        return event

    @contextmanager
    def span(self, kind, **data):
        event = self.emit(kind, **data)
        token = parent_span.set(event["id"])
        started = time.perf_counter()
        try:
            yield event
        except BaseException as exc:
            event["error"] = str(exc) or type(exc).__name__
            raise
        finally:
            event["seconds"] = time.perf_counter() - started
            parent_span.reset(token)
