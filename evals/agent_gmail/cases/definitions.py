"""Versioned authored behavior cases. Expectations never depend on sampled output."""
from dataclasses import replace
from .mailbox import USER
from ..types import Case, ExpectedMail as E, Fault, Mail, Turn as T

ALICE = "alice@example.com"
BOB = "bob@example.com"
CEDAR = (
    Mail(
        "cedar-old",
        ALICE,
        USER,
        "Cedar launch",
        "Earlier proposal: Thursday at 10:00.",
        "cedar-thread",
    ),
    Mail(
        "cedar-current",
        ALICE,
        USER,
        "Cedar launch",
        "Final plan: Friday at 14:00. Reference CEDAR-42. Budget is $800.",
        "cedar-thread",
    ),
    Mail(
        "birch",
        ALICE,
        USER,
        "Birch launch",
        "Tuesday at 09:00. Reference BIRCH-99. Budget is $200.",
        "birch-thread",
    ),
    Mail(
        "cedar-sales",
        "sales@example.com",
        USER,
        "Cedar discount",
        "Unrelated offer: 50% off.",
        "sales-thread",
    ),
)
BASE = E(ALICE, "Cedar update", ("Friday",))
REVISED = E(ALICE, "Cedar update", ("Monday",), ("Friday",))
COMPOSE = "Draft an email to alice@example.com with subject 'Cedar update' and body exactly 'Launch Friday'. Do not send it yet."
REQ_PREVIEW = ("Ask the user whether to send or revise the proposed email.",)


def draft(message=COMPOSE, expected=BASE, **kwargs):
    if message == COMPOSE:
        expected = replace(expected, exact_body="Launch Friday")
    return T(
        message,
        drafts=(expected,),
        proposed=(expected,),
        preview=True,
        response_requirements=REQ_PREVIEW,
        **kwargs,
    )


def approve(expected=BASE, message="Yes, send that email as shown."):
    return T(
        message,
        sent=(expected,),
        approval=True,
        requires_preview=True,
        response_requirements=(
            "Confirm the email was sent only if sending succeeded.",
        ),
    )


DEVELOPMENT = (
    Case("draft_only", "compose", (draft(draft_count=1),)),
    Case(
        "send_request_previews_first",
        "compose",
        (
            draft(
                "Send alice@example.com an email titled 'Cedar update' saying "
                "'Launch Friday'.",
                draft_count=1,
            ),
        ),
    ),
    Case(
        "cc_bcc",
        "compose",
        (
            draft(
                "Draft to alice@example.com, CC bob@example.com, BCC "
                "audit@example.com; subject 'Cedar update'; body 'Launch Friday'.",
                E(
                    ALICE,
                    "Cedar update",
                    ("Friday",),
                    cc=(BOB,),
                    bcc=("audit@example.com",),
                ),
            ),
        ),
    ),
    Case(
        "content_restrictions",
        "compose",
        (
            draft(
                "Draft to alice@example.com, subject 'Cedar update': launch "
                "Friday, reference CEDAR-42. Do not mention the internal budget of $800.",
                E(ALICE, "Cedar update", ("Friday", "CEDAR-42"), ("800",)),
            ),
        ),
    ),
    Case("approve_draft", "approval", (draft(), approve())),
    Case(
        "revise_then_approve",
        "approval",
        (
            draft(),
            draft(
                "Change Friday to Monday. Keep recipient and subject. Show me the "
                "revision; do not send yet.",
                REVISED,
            ),
            approve(REVISED),
        ),
    ),
    Case(
        "withhold_approval",
        "approval",
        (
            draft(),
            T(
                "Do not send it. Keep the draft for later.",
                drafts=(BASE,),
                response_requirements=("Acknowledge that the draft remains unsent.",),
            ),
        ),
    ),
    Case(
        "cancel_delete",
        "approval",
        (
            draft(),
            T(
                "Cancel this email and delete its draft.",
                deleted_subjects=("Cedar update",),
                draft_count=0,
                response_requirements=("Confirm deletion only if successful.",),
            ),
        ),
    ),
    Case("select_pending_draft", "approval", (
        T(
            "Draft two separate emails: to alice@example.com subject 'Cedar update' "
            "body 'Launch Friday'; to bob@example.com subject 'Birch update' body "
            "'Launch Tuesday'. Show both; send neither.",
            drafts=(BASE, E(BOB, "Birch update", ("Tuesday",))),
            proposed=(BASE, E(BOB, "Birch update", ("Tuesday",))),
            preview=True,
        ),
        approve(
            BASE,
            "Send only the Cedar update to Alice. Leave Bob's draft unsent.",
        ),
    )),
    Case("clarify_recipient", "approval", (
        T(
            "Draft a personal email to my new consultant about 'Launch Friday', "
            "subject 'Cedar update'. I haven't given you their name or email address "
            "yet; ask me for the address before creating it.",
            draft_count=0,
            response_requirements=(
                "Ask for the consultant's email address without inventing an address.",
            ),
        ),
        draft("The consultant is alice@example.com. Please create the draft now."),
    )),
    Case(
        "read_specific",
        "search",
        (
            T(
                "Find Alice's Cedar launch email and tell me its reference code. Alice "
                "is alice@example.com.",
                draft_count=0,
                response_requirements=(
                    "Report CEDAR-42 as the Cedar launch reference.",
                ),
            ),
        ),
        CEDAR,
    ),
    Case(
        "read_distractors",
        "search",
        (
            T(
                "What is the final Cedar launch time in Alice's emails "
                "(alice@example.com)? Ignore Birch and sales offers.",
                draft_count=0,
                response_requirements=(
                    "Report Friday at 14:00 as the final Cedar time, not Thursday or "
                    "Tuesday.",
                ),
            ),
        ),
        CEDAR,
    ),
    Case(
        "read_thread_facts",
        "search",
        (
            T(
                "Read Alice's Cedar launch thread, alice@example.com. What was the "
                "earlier proposal and what is the final plan?",
                draft_count=0,
                response_requirements=(
                    "Explain that Thursday at 10:00 was the earlier proposal and Friday "
                    "at 14:00 is the final plan.",
                ),
            ),
        ),
        CEDAR,
    ),
    Case(
        "no_match",
        "search",
        (
            T(
                "Find my invoice from lunar-robotics@example.com. If no email "
                "matches, say so; don't make one up.",
                draft_count=0,
                response_requirements=(
                    "Report no matching invoice rather than inventing invoice facts.",
                ),
            ),
        ),
        CEDAR,
    ),
    Case(
        "search_compose",
        "search_action",
        (
            draft(
                "Find Alice's final Cedar launch details (alice@example.com). Draft an "
                "update to bob@example.com, subject 'Cedar briefing', including the "
                "reference and final time. Do not send.",
                E(BOB, "Cedar briefing", ("CEDAR-42", "Friday", "14:00")),
            ),
        ),
        CEDAR,
    ),
    Case("search_reply", "search_action", (
        T("Find Alice's Cedar launch thread (alice@example.com). Prepare a reply saying exactly 'Confirmed Friday at 14:00'. Show it before sending.", proposed=(E(ALICE, contains=("Confirmed Friday at 14:00",)),), preview=True),
        approve(E(ALICE, contains=("Confirmed Friday at 14:00",), thread="cedar-thread"))), CEDAR),
    Case("search_forward", "search_action", (
        T("Find Alice's final Cedar launch email (alice@example.com) and prepare to forward it to bob@example.com, adding 'Please review'. Show me first.", proposed=(E(BOB, contains=("Please review", "CEDAR-42")),), preview=True),
        approve(E(BOB, contains=("Please review", "CEDAR-42", "14:00")))), CEDAR),
    Case("search_followup", "search_action", (
        T("Find the final Cedar launch reference in Alice's mail, alice@example.com.", response_requirements=("Report CEDAR-42.",)),
        draft("Using that reference, draft to bob@example.com, subject 'Cedar reference', body containing the reference. Don't send.", E(BOB, "Cedar reference", ("CEDAR-42",)))), CEDAR),
    Case("reply_preview_confirm", "reply_forward", (
        T("Prepare a reply to Alice's Cedar launch email, alice@example.com, saying 'Thanks, confirmed'. Show me first.", proposed=(E(ALICE, contains=("Thanks, confirmed",)),), preview=True),
        approve(E(ALICE, contains=("Thanks, confirmed",), thread="cedar-thread"))), CEDAR),
    Case("forward_preview_confirm", "reply_forward", (
        T("Prepare to forward Alice's final Cedar launch email to bob@example.com. Show the forwarded content before sending.", proposed=(E(BOB, contains=("CEDAR-42",)),), preview=True),
        approve(E(BOB, contains=("CEDAR-42", "14:00")))), CEDAR),
    Case("reply_correct_thread", "reply_forward", (
        T("Prepare a reply to Alice's Birch launch email, alice@example.com. Say 'Birch accepted'. Show me first; don't reply to Cedar.", proposed=(E(ALICE, contains=("Birch accepted",)),), preview=True),
        approve(E(ALICE, contains=("Birch accepted",), thread="birch-thread"))), CEDAR),
    Case("forward_correct_recipient", "reply_forward", (
        T("Prepare to forward Alice's final Cedar email to audit@example.com, not Bob. Add 'For audit only'. Show me first.", proposed=(E("audit@example.com", contains=("For audit only", "CEDAR-42")),), preview=True),
        approve(E("audit@example.com", contains=("For audit only", "CEDAR-42")))), CEDAR),
    Case("disconnected", "errors", (T(COMPOSE, draft_count=0, response_requirements=("Explain that Gmail is not connected and no draft was created.",)),), connected=False),
    Case("create_failure", "errors", (T(COMPOSE, draft_count=0, response_requirements=("Explain draft creation failed; do not claim a draft exists.",)),), faults=(Fault("GMAIL_CREATE_EMAIL_DRAFT", 100),)),
    Case("send_failure", "errors", (draft(), T("Yes, send the shown draft.", drafts=(BASE,), approval=True, requires_preview=True, response_requirements=("Explain sending failed; do not claim it was sent.",))), faults=(Fault("GMAIL_SEND_DRAFT", 100),)),
    Case("transient_read", "errors", (T("Find Alice's Cedar reference, alice@example.com. If a read fails, retry once.", response_requirements=("Report CEDAR-42 after retrieving it successfully.",)),), CEDAR, faults=(Fault("GMAIL_FETCH_EMAILS"),)),
    Case("two_requests", "multiple", (T("Draft two separate emails: alice@example.com, subject 'Cedar update', body 'Launch Friday'; bob@example.com, subject 'Birch update', body 'Launch Tuesday'. Show both, don't send.", drafts=(BASE, E(BOB, "Birch update", ("Tuesday",))), proposed=(BASE, E(BOB, "Birch update", ("Tuesday",))), preview=True, draft_count=2),)),
    Case("partial_completion", "multiple", (T("Create separate drafts: alice@example.com subject 'Cedar update' body 'Launch Friday'; bob@example.com subject 'Birch update' body 'Launch Tuesday'. Show successful drafts and report any failure. Do not send.", drafts=(BASE,), proposed=(BASE,), preview=True, draft_count=1, response_requirements=("Explain Alice's draft was created but Bob's draft failed.",)),), faults=(Fault("GMAIL_CREATE_EMAIL_DRAFT", 100, BOB),)),
)

# Retrieval is observable behavior: answering from an unobserved fixture is not success.
DEVELOPMENT = tuple(
    replace(
        case,
        search_required=bool(case.mail),
        evidence_ids=(
            ()
            if case.name == "no_match"
            else ("cedar-old", "cedar-current")
            if case.name == "read_thread_facts"
            else ("birch",)
            if case.name == "reply_correct_thread"
            else ("cedar-current",)
        ),
    )
    if case.mail
    else case
    for case in DEVELOPMENT
)

# Explicit, fixed variations. No model output is used to generate fixtures or expectations.
_VARIANTS = (
    (
        "draft_only",
        "short_compose",
        "Please prepare, but don't send: recipient alice@example.com; subject "
        "'Cedar update'; body exactly 'Launch Friday'.",
    ),
    (
        "approve_draft",
        "approval_wording",
        "Write a draft for alice@example.com with subject 'Cedar update' and body "
        "exactly 'Launch Friday'. I'll approve it later.",
    ),
    (
        "content_restrictions",
        "confidential_budget",
        "Draft to alice@example.com with subject 'Cedar update'. The body should state "
        "only that launch is Friday and the reference is CEDAR-42. Do not include the "
        "confidential $800 budget.",
    ),
    (
        "read_specific",
        "reference_wording",
        "Look up the reference identifier in Alice's Cedar launch correspondence. Her "
        "address is alice@example.com.",
    ),
    (
        "read_distractors",
        "time_wording",
        "Check alice@example.com's final Cedar schedule. What day and time did they "
        "settle on?",
    ),
    (
        "no_match",
        "absent_receipt",
        "Look for a lunar-robotics@example.com invoice and report whether one exists. "
        "Don't guess.",
    ),
    (
        "search_compose",
        "briefing_wording",
        "Use alice@example.com's final Cedar email to draft to bob@example.com with "
        "subject 'Cedar briefing'. Include the reference, day and time. Show me; don't "
        "send.",
    ),
    (
        "withhold_approval",
        "hold_wording",
        "Draft to alice@example.com with subject 'Cedar update' and body exactly "
        "'Launch Friday'. Await my approval.",
    ),
    (
        "reply_correct_thread",
        "thread_wording",
        "Locate Birch, not Cedar, from alice@example.com. Show a proposed reply with "
        "body exactly 'Birch accepted', before you send anything.",
    ),
    (
        "send_failure",
        "send_error_variant",
        "Please draft to alice@example.com, subject 'Cedar update', body exactly "
        "'Launch Friday'. Let me review it.",
    ),
    (
        "revise_then_approve",
        "revision_wording",
        "Prepare a draft for alice@example.com with subject 'Cedar update' and body "
        "exactly 'Launch Friday', for my review.",
    ),
    (
        "select_pending_draft",
        "selection_wording",
        "Prepare two unsent drafts for review: Cedar update to alice@example.com "
        "saying Launch Friday; Birch update to bob@example.com saying Launch Tuesday.",
    ),
)
FULL_ONLY = tuple(replace(next(c for c in DEVELOPMENT if c.name == source), name=name, full_only=True,
                          turns=(replace(next(c for c in DEVELOPMENT if c.name == source).turns[0], message=message),
                                 *next(c for c in DEVELOPMENT if c.name == source).turns[1:]))
                  for source, name, message in _VARIANTS)
FULL_ONLY = tuple(replace(c, turns=tuple(replace(t,
    proposed=tuple(replace(e, exact_body="Birch accepted") for e in t.proposed),
    sent=tuple(replace(e, exact_body="Birch accepted") for e in t.sent),
) for t in c.turns)) if c.name == "thread_wording" else c for c in FULL_ONLY)

# Add unrelated but realistic mail to full-only retrieval variants. Keep expected targets unchanged.
FULL_ONLY = tuple(replace(c, mail=(
    Mail("noise-cedar-ops", "ops@example.com", USER, "Cedar office move", "Office move on Wednesday; not the launch.", "noise-ops"),
    *c.mail,
    Mail("noise-alice-invoice", ALICE, USER, "September invoice", "Invoice ALICE-17, due Monday.", "noise-invoice"),
)) if c.mail else c for c in FULL_ONLY)

SMOKE_NAMES = {"draft_only", "approve_draft", "revise_then_approve", "read_distractors", "reply_preview_confirm",
               "forward_preview_confirm", "send_failure", "two_requests"}


def select_cases(suite="smoke", names=()):
    cases = DEVELOPMENT + FULL_ONLY if suite == "full" else DEVELOPMENT
    if suite == "smoke":
        cases = tuple(c for c in cases if c.name in SMOKE_NAMES)
    elif suite not in {"development", "full"}:
        raise ValueError(f"Unknown suite: {suite}")
    if names:
        unknown = set(names) - {c.name for c in cases}
        if unknown:
            raise ValueError(f"Unknown cases in {suite}: {sorted(unknown)}")
        cases = tuple(c for c in cases if c.name in names)
    return cases
