"""Immutable input and expectation contracts, independent of model output."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Mail:
    id: str
    sender: str
    to: str
    subject: str
    body: str
    thread: str = ""
    draft: bool = False


@dataclass(frozen=True)
class ExpectedMail:
    to: str
    subject: str | None = None
    contains: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    thread: str | None = None
    exact_body: str | None = None


@dataclass(frozen=True)
class Turn:
    message: str
    drafts: tuple[ExpectedMail, ...] = ()
    sent: tuple[ExpectedMail, ...] = ()
    proposed: tuple[ExpectedMail, ...] = ()
    preview: bool = False
    approval: bool = False
    requires_preview: bool = False
    response_requirements: tuple[str, ...] = ()
    deleted_subjects: tuple[str, ...] = ()
    # None allows unrequested pending draft retention (never extra transmissions).
    draft_count: int | None = None


@dataclass(frozen=True)
class Fault:
    action: str
    count: int = 1
    recipient: str | None = None


@dataclass(frozen=True)
class Case:
    name: str
    family: str
    turns: tuple[Turn, ...]
    mail: tuple[Mail, ...] = ()
    faults: tuple[Fault, ...] = ()
    connected: bool = True
    full_only: bool = False
    search_required: bool = False
    evidence_ids: tuple[str, ...] = ()
