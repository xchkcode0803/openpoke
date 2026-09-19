"""Hand-authored routing scenarios and deterministic roster variants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random
from typing import Literal


TurnSource = Literal["user", "execution_agent"]
ExpectedAction = Literal["delegate", "clarify", "respond", "wait"]
RouteKind = Literal["reuse", "create"]
ConversationEntry = tuple[str, str]


@dataclass(frozen=True)
class ExpectedDelegation:
    task_key: str
    route: RouteKind
    acceptable_agent_names: tuple[str, ...] = ()
    required_facts: tuple[str, ...] = ()
    forbidden_facts: tuple[str, ...] = ()
    agent_from_task: str | None = None


@dataclass(frozen=True)
class RoutingTurn:
    source: TurnSource
    message: str
    expected_action: ExpectedAction
    delegations: tuple[ExpectedDelegation, ...] = ()
    response_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutingCase:
    name: str
    description: str
    initial_agents: tuple[str, ...]
    initial_conversation: tuple[ConversationEntry, ...]
    turns: tuple[RoutingTurn, ...]
    tags: frozenset[str]
    initial_summary: str = ""


def reuse(
    task_key: str,
    *agent_names: str,
    required_facts: tuple[str, ...] = (),
    forbidden_facts: tuple[str, ...] = (),
    agent_from_task: str | None = None,
) -> ExpectedDelegation:
    return ExpectedDelegation(
        task_key=task_key,
        route="reuse",
        acceptable_agent_names=agent_names,
        required_facts=required_facts,
        forbidden_facts=forbidden_facts,
        agent_from_task=agent_from_task,
    )


def create(
    task_key: str,
    *required_facts: str,
    forbidden_facts: tuple[str, ...] = (),
) -> ExpectedDelegation:
    return ExpectedDelegation(
        task_key=task_key,
        route="create",
        required_facts=required_facts,
        forbidden_facts=forbidden_facts,
    )


def user(
    message: str,
    expected_action: ExpectedAction,
    *delegations: ExpectedDelegation,
    response_requirements: tuple[str, ...] = (),
) -> RoutingTurn:
    return RoutingTurn("user", message, expected_action, delegations, response_requirements)


def worker(
    message: str,
    expected_action: ExpectedAction,
    *delegations: ExpectedDelegation,
    response_requirements: tuple[str, ...] = (),
) -> RoutingTurn:
    return RoutingTurn("execution_agent", message, expected_action, delegations, response_requirements)


def _case(
    name: str,
    description: str,
    agents: tuple[str, ...],
    turns: tuple[RoutingTurn, ...],
    *tags: str,
    conversation: tuple[ConversationEntry, ...] = (),
    summary: str = "",
) -> RoutingCase:
    return RoutingCase(name, description, agents, conversation, turns, frozenset(tags), summary)


DEVELOPMENT_CASES: tuple[RoutingCase, ...] = (
    # Core routing: 7
    _case(
        "creates_agent_for_new_task",
        "Creates work when no existing agent can own it.",
        (),
        (user("Help me compare compact coffee grinders.", "delegate", create("coffee_grinder", "compare compact coffee grinders")),),
        "development", "core", "smoke",
    ),
    _case(
        "reuses_existing_hotel_search_agent",
        "Continues a clear hotel-search task.",
        ("Montreal Hotel Search",),
        (user("Find three more hotels near Old Montreal.", "delegate", reuse("hotels", "Montreal Hotel Search", required_facts=("find more hotels near Old Montreal",))),),
        "development", "core", "smoke",
    ),
    _case(
        "selects_agent_from_unrelated_roster",
        "Chooses one clear owner among unrelated work.",
        ("Monthly Rent Reminder", "Electricity Bill", "Maya Birthday Dinner", "Montreal Flight Search"),
        (user("Did Maya confirm the dinner reservation?", "delegate", reuse("maya_dinner", "Maya Birthday Dinner", required_facts=("check whether Maya confirmed dinner",))),),
        "development", "core", "smoke",
    ),
    _case(
        "routes_two_existing_tasks",
        "Routes two independent requests to their existing owners.",
        ("Montreal Flight Search", "Monthly Rent Reminder"),
        (user("Check cheaper Montreal flights and tell me when rent is due.", "delegate", reuse("flights", "Montreal Flight Search", required_facts=("check cheaper Montreal flights",)), reuse("rent", "Monthly Rent Reminder", required_facts=("tell the user when rent is due",))),),
        "development", "core",
    ),
    _case(
        "preserves_draft_only_restriction",
        "Routes to the right owner and keeps the no-send restriction.",
        ("Email Landlord About Kitchen Leak",),
        (user("Draft a follow-up about the repair date, but do not send it.", "delegate", reuse("landlord", "Email Landlord About Kitchen Leak", required_facts=("draft a follow-up about the repair date", "do not send"), forbidden_facts=("send the email",))),),
        "development", "core", "smoke", "semantic",
    ),
    _case(
        "avoids_duplicate_agent_for_paraphrased_follow_up",
        "Reuses an agent even though the request uses different wording.",
        ("Cancel Gym Membership", "Monthly Rent Reminder"),
        (user("Any news on ending my gym contract?", "delegate", reuse("gym", "Cancel Gym Membership", required_facts=("check the gym membership cancellation",))),),
        "development", "core",
    ),
    _case(
        "routes_existing_and_new_task",
        "Reuses one owner while creating another for independent new work.",
        ("Maya Birthday Dinner",),
        (user("Check whether Maya confirmed dinner and compare compact coffee grinders.", "delegate", reuse("maya_dinner", "Maya Birthday Dinner", required_facts=("check whether Maya confirmed dinner",)), create("coffee_grinder", "compare compact coffee grinders")),),
        "development", "core",
    ),
    # Conversation context: 4
    _case(
        "uses_conversation_to_resolve_pronoun",
        "Uses the visible conversation to resolve a pronoun.",
        ("Email Maya About Apartment", "Maya Birthday Dinner"),
        (user("Did she reply?", "delegate", reuse("maya_dinner", "Maya Birthday Dinner", required_facts=("check Maya's dinner reply",))),),
        "development", "conversation", "smoke",
        conversation=(("user_message", "Please ask Maya whether Saturday dinner still works."), ("poke_reply", "I will check with Maya about dinner.")),
    ),
    _case(
        "uses_conversation_to_resolve_omitted_trip_subject",
        "Uses recent discussion rather than agent-name similarity alone.",
        ("Montreal Hotel Search", "Montreal Flight Search", "Montreal Restaurant Reservations"),
        (user("Can we find cheaper ones?", "delegate", reuse("hotels", "Montreal Hotel Search", required_facts=("find cheaper Montreal hotels",))),),
        "development", "conversation",
        conversation=(("user_message", "The Montreal hotels are more expensive than I expected."), ("poke_reply", "I can look for lower-cost hotel options.")),
    ),
    _case(
        "uses_summary_to_route_follow_up",
        "Uses visible working-memory summary when raw conversation is empty.",
        ("Dentist Appointment", "Annual Eye Exam"),
        (user("Can you keep looking for an earlier opening?", "delegate", reuse("dentist", "Dentist Appointment", required_facts=("find an earlier dentist appointment",))),),
        "development", "conversation", "summary",
        summary="The user is trying to move a dentist appointment earlier and asked OpenPoke to search for openings.",
    ),
    _case(
        "uses_latest_topic_after_user_correction",
        "Follows the user's correction instead of the older topic.",
        ("Montreal Hotel Search", "Montreal Flight Search"),
        (user("Actually, focus on flights, not hotels.", "delegate", reuse("flights", "Montreal Flight Search", required_facts=("focus on Montreal flights",))),),
        "development", "conversation",
        conversation=(("user_message", "Please find Montreal hotels."), ("poke_reply", "I will look at hotels.")),
    ),
    # Routing across turns: 3
    _case(
        "reuses_agent_created_earlier_in_conversation",
        "Creates an agent then reuses that exact owner later.",
        (),
        (
            user("Help me plan a birthday dinner for Maya.", "delegate", create("maya_dinner", "plan Maya's birthday dinner")),
            user("Can you find a few restaurant options for it?", "delegate", reuse("maya_dinner_follow_up", required_facts=("find restaurant options for Maya's birthday dinner",), agent_from_task="maya_dinner")),
        ),
        "development", "multi_turn", "smoke",
    ),
    _case(
        "returns_to_original_agent_after_topic_switch",
        "Does not favor the newest agent after a topic switch.",
        (),
        (
            user("Help me find a new carry-on suitcase.", "delegate", create("suitcase", "find a carry-on suitcase")),
            user("Also compare coffee grinders.", "delegate", create("coffee", "compare coffee grinders")),
            user("Back to the suitcase: find lighter options.", "delegate", reuse("suitcase_follow_up", required_facts=("find lighter carry-on suitcase options",), agent_from_task="suitcase")),
        ),
        "development", "multi_turn",
    ),
    _case(
        "routes_after_clarification_answer",
        "Asks first, then routes using the user's answer.",
        ("Email Maya About Apartment", "Maya Birthday Dinner"),
        (
            user("Did Maya reply?", "clarify", response_requirements=("ask whether the user means the apartment or dinner conversation",)),
            user("The dinner reservation.", "delegate", reuse("maya_dinner", "Maya Birthday Dinner", required_facts=("check Maya's dinner reservation reply",))),
        ),
        "development", "multi_turn", "smoke", "semantic",
    ),
    # Execution-agent updates: 3
    _case(
        "reports_completed_worker_update_without_redelegating",
        "Reports a completed worker result without restarting the task.",
        ("Montreal Hotel Search",),
        (worker("[SUCCESS] Montreal Hotel Search: I found three hotels near Old Montreal.", "respond", response_requirements=("report the hotel options",)),),
        "development", "worker_update", "smoke", "semantic",
    ),
    _case(
        "routes_requested_next_step_after_worker_update",
        "Continues an explicitly requested next step after a worker result.",
        ("Email Landlord About Kitchen Leak",),
        (worker("[SUCCESS] Email Landlord About Kitchen Leak: The landlord offered Tuesday at 10 AM.", "delegate", reuse("landlord", "Email Landlord About Kitchen Leak", required_facts=("draft a reply about Tuesday at 10 AM", "do not send"), forbidden_facts=("send the reply",))),),
        "development", "worker_update", "semantic",
        conversation=(("user_message", "When the landlord replies, draft a response but do not send it."),),
    ),
    _case(
        "waits_for_duplicate_worker_update",
        "Avoids a duplicate user-visible response when the same result is already present.",
        ("Montreal Hotel Search",),
        (worker("[SUCCESS] Montreal Hotel Search: I found three hotels near Old Montreal.", "wait"),),
        "development", "worker_update",
        conversation=(("agent_message", "[SUCCESS] Montreal Hotel Search: I found three hotels near Old Montreal."), ("poke_reply", "I found three hotels near Old Montreal.")),
    ),
    # Confusing choices: 6
    _case(
        "distinguishes_same_person_different_tasks",
        "Selects the task owner rather than any agent involving Maya.",
        ("Maya Birthday Dinner", "Email Maya About Apartment", "Maya Travel Plans"),
        (user("Did Maya agree to the dinner time?", "delegate", reuse("dinner", "Maya Birthday Dinner", required_facts=("check Maya's dinner time reply",))),),
        "development", "confusing", "smoke",
    ),
    _case(
        "distinguishes_same_task_different_subjects",
        "Selects the matching subject among similar search agents.",
        ("Montreal Hotel Search", "Chicago Hotel Search", "Toronto Hotel Search"),
        (user("Find more hotel choices in Toronto.", "delegate", reuse("toronto", "Toronto Hotel Search", required_facts=("find more Toronto hotels",))),),
        "development", "confusing",
    ),
    _case(
        "selects_specialized_agent_over_broad_agent",
        "Selects a focused task owner rather than broad trip planning.",
        ("Montreal Trip Planning", "Montreal Hotel Search", "Montreal Restaurant Reservations"),
        (user("Show me more hotels near Old Montreal.", "delegate", reuse("hotels", "Montreal Hotel Search", required_facts=("show more hotels near Old Montreal",))),),
        "development", "confusing",
    ),
    _case(
        "selects_broad_agent_for_trip_wide_change",
        "Selects the parent owner when the whole trip changes.",
        ("Montreal Trip Planning", "Montreal Hotel Search", "Montreal Restaurant Reservations"),
        (user("Move the trip from four days to six and rebalance everything.", "delegate", reuse("trip", "Montreal Trip Planning", required_facts=("extend the Montreal trip and rebalance the itinerary",))),),
        "development", "confusing",
    ),
    _case(
        "selects_current_tax_filing_agent",
        "Uses the current year rather than an older filing.",
        ("2025 Tax Documents", "2026 Tax Documents"),
        (user("Continue this year's tax filing.", "delegate", reuse("taxes", "2026 Tax Documents", required_facts=("continue the 2026 tax filing",))),),
        "development", "confusing",
    ),
    _case(
        "accepts_either_equivalent_agent",
        "Allows either of two truly interchangeable owners.",
        ("Monthly Electricity Bill", "Electricity Bill Follow-up"),
        (user("What was the electricity amount this month?", "delegate", reuse("electricity", "Monthly Electricity Bill", "Electricity Bill Follow-up", required_facts=("find this month's electricity amount",))),),
        "development", "confusing",
    ),
    # Negative overload: 3
    _case(
        "creates_new_agent_when_similar_roster_has_no_owner",
        "Does not force a new task into a related existing agent.",
        ("Montreal Hotel Search", "Montreal Flight Search", "Montreal Restaurant Reservations"),
        (user("Research whether I should move to Montreal permanently.", "delegate", create("montreal_move", "research moving to Montreal permanently")),),
        "development", "negative", "smoke",
    ),
    _case(
        "clarifies_ambiguous_request_under_large_roster",
        "Does not guess when two visible owners remain equally plausible.",
        ("Email Maya About Apartment", "Maya Birthday Dinner", "Montreal Hotel Search"),
        (user("Did Maya reply?", "clarify", response_requirements=("ask which Maya conversation the user means",)),),
        "development", "negative", "semantic",
    ),
    _case(
        "does_not_delegate_simple_response_under_large_roster",
        "Does not delegate merely because many agents are visible.",
        ("Montreal Hotel Search", "Monthly Rent Reminder", "Cancel Gym Membership"),
        (user("Thanks.", "respond"),),
        "development", "negative",
    ),
)


HELD_OUT_CASES: tuple[RoutingCase, ...] = (
    _case("held_out_reuses_renewal_agent", "Resumes an insurance renewal.", ("Car Insurance Renewal",), (user("Did the insurer send the updated quote?", "delegate", reuse("renewal", "Car Insurance Renewal", required_facts=("check the updated car insurance quote",))),), "held_out", "core"),
    _case("held_out_creates_new_home_project", "Separates a new home project from old repair work.", ("Email Landlord About Kitchen Leak",), (user("Help me compare air purifiers for my bedroom.", "delegate", create("air_purifier", "compare bedroom air purifiers")),), "held_out", "negative"),
    _case("held_out_uses_context_for_terse_follow_up", "Uses the latest visible topic for a terse follow-up.", ("Dentist Appointment", "Annual Eye Exam"), (user("Any earlier options?", "delegate", reuse("dentist", "Dentist Appointment", required_facts=("find earlier dentist options",))),), "held_out", "conversation", conversation=(("user_message", "Please find an earlier dentist appointment."),)),
    _case("held_out_routes_two_existing_tasks", "Covers two independent requests.", ("Montreal Flight Search", "Monthly Rent Reminder"), (user("Check cheaper Montreal flights and remind me when rent is due.", "delegate", reuse("flights", "Montreal Flight Search", required_facts=("check cheaper Montreal flights",)), reuse("rent", "Monthly Rent Reminder", required_facts=("check when rent is due",))),), "held_out", "multi_task"),
    _case("held_out_preserves_no_purchase_restriction", "Keeps a purchase restriction in delegated work.", ("Laptop Purchase Research",), (user("Find lightweight laptops, but do not buy anything.", "delegate", reuse("laptop", "Laptop Purchase Research", required_facts=("find lightweight laptops", "do not buy"), forbidden_facts=("buy a laptop",))),), "held_out", "semantic"),
    _case("held_out_reports_worker_update", "Reports a scripted worker result.", ("Dentist Appointment",), (worker("[SUCCESS] Dentist Appointment: An opening is available Tuesday at 9 AM.", "respond", response_requirements=("report the Tuesday opening",)),), "held_out", "worker_update", "semantic"),
)


REGRESSION_CASES: tuple[RoutingCase, ...] = ()


def validate_cases(cases: tuple[RoutingCase, ...]) -> None:
    names: set[str] = set()
    for case in cases:
        if case.name in names:
            raise ValueError(f"duplicate case name: {case.name}")
        names.add(case.name)
        if len(case.initial_agents) != len(set(case.initial_agents)):
            raise ValueError(f"duplicate initial agents: {case.name}")
        created_tasks: set[str] = set()
        for turn in case.turns:
            if turn.expected_action == "delegate" and not turn.delegations:
                raise ValueError(f"delegation expected without targets: {case.name}")
            if turn.expected_action != "delegate" and turn.delegations:
                raise ValueError(f"delegations on non-routing turn: {case.name}")
            for expected in turn.delegations:
                if expected.route == "reuse" and not (expected.acceptable_agent_names or expected.agent_from_task):
                    raise ValueError(f"reuse expectation has no target: {case.name}")
                if expected.route == "create":
                    created_tasks.add(expected.task_key)
                if expected.agent_from_task and expected.agent_from_task not in created_tasks:
                    raise ValueError(f"unknown created-agent reference: {case.name}")


def add_unrelated_agents(case: RoutingCase, count: int, seed: int) -> RoutingCase:
    rng = Random(seed)
    topics = ("Library Card", "Coffee Grinder", "Eye Exam", "Streaming Subscription", "Air Filter", "Carry On Luggage", "Birthday Cake", "Plant Delivery")
    candidates = [f"{topic} Follow-up {index:04d}" for topic in topics for index in range(1, 1000)]
    rng.shuffle(candidates)
    available = [name for name in candidates if name not in case.initial_agents]
    return replace(
        case,
        name=f"{case.name}__unrelated_{count}_seed_{seed}",
        initial_agents=case.initial_agents + tuple(available[:count]),
        tags=case.tags | frozenset({"overload"}),
    )


def add_similar_agents(case: RoutingCase, target_name: str, count: int, seed: int) -> RoutingCase:
    rng = Random(seed)
    candidates = [f"{target_name} Related Thread {index:04d}" for index in range(1, count + 1)]
    rng.shuffle(candidates)
    return replace(
        case,
        name=f"{case.name}__similar_{count}_seed_{seed}",
        initial_agents=case.initial_agents + tuple(candidates),
        tags=case.tags | frozenset({"overload", "similar_agents"}),
    )


def move_target_agent(case: RoutingCase, target_name: str, position: Literal["first", "middle", "last"]) -> RoutingCase:
    agents = [name for name in case.initial_agents if name != target_name]
    if position == "first":
        agents.insert(0, target_name)
    elif position == "middle":
        agents.insert(len(agents) // 2, target_name)
    else:
        agents.append(target_name)
    return replace(
        case,
        name=f"{case.name}__target_{position}",
        initial_agents=tuple(agents),
        tags=case.tags | frozenset({"stability"}),
    )


def shuffle_roster(case: RoutingCase, seed: int) -> RoutingCase:
    agents = list(case.initial_agents)
    Random(seed).shuffle(agents)
    return replace(
        case,
        name=f"{case.name}__shuffle_{seed}",
        initial_agents=tuple(agents),
        tags=case.tags | frozenset({"stability"}),
    )


def all_cases() -> tuple[RoutingCase, ...]:
    return DEVELOPMENT_CASES + HELD_OUT_CASES + REGRESSION_CASES


def _named_case(name: str) -> RoutingCase:
    return next(case for case in DEVELOPMENT_CASES if case.name == name)


def smoke_cases() -> tuple[RoutingCase, ...]:
    names = {
        "creates_agent_for_new_task",
        "reuses_existing_hotel_search_agent",
        "preserves_draft_only_restriction",
        "uses_conversation_to_resolve_pronoun",
        "reuses_agent_created_earlier_in_conversation",
        "routes_after_clarification_answer",
        "reports_completed_worker_update_without_redelegating",
        "distinguishes_same_person_different_tasks",
        "creates_new_agent_when_similar_roster_has_no_owner",
        "routes_existing_and_new_task",
    }
    authored = tuple(case for case in DEVELOPMENT_CASES if case.name in names)
    return authored + (
        add_unrelated_agents(_named_case("reuses_existing_hotel_search_agent"), 100, 11),
        add_unrelated_agents(_named_case("creates_new_agent_when_similar_roster_has_no_owner"), 100, 13),
    )


def standard_cases() -> tuple[RoutingCase, ...]:
    representative = (
        _named_case("reuses_existing_hotel_search_agent"),
        _named_case("creates_new_agent_when_similar_roster_has_no_owner"),
        _named_case("uses_conversation_to_resolve_pronoun"),
        _named_case("routes_two_existing_tasks") if any(case.name == "routes_two_existing_tasks" for case in DEVELOPMENT_CASES) else _named_case("selects_agent_from_unrelated_roster"),
    )
    return DEVELOPMENT_CASES + tuple(add_unrelated_agents(case, 100, 20 + index) for index, case in enumerate(representative))


def full_cases() -> tuple[RoutingCase, ...]:
    reuse_seed = _named_case("reuses_existing_hotel_search_agent")
    create_seed = _named_case("creates_new_agent_when_similar_roster_has_no_owner")
    context_seed = _named_case("uses_conversation_to_resolve_pronoun")
    confusing_seed = _named_case("distinguishes_same_person_different_tasks")
    variants: list[RoutingCase] = []
    for seed_index, seed_case in enumerate((reuse_seed, create_seed, context_seed, confusing_seed)):
        for size in (10, 50, 100, 250, 500, 1000):
            variants.append(add_unrelated_agents(seed_case, size, 100 + seed_index * 10 + size))
    for count in (5, 25, 100, 250):
        variants.append(add_similar_agents(reuse_seed, "Montreal Hotel Search", count, 200 + count))
        variants.append(add_similar_agents(confusing_seed, "Maya Birthday Dinner", count, 300 + count))
    for position in ("first", "middle", "last"):
        variants.append(move_target_agent(reuse_seed, "Montreal Hotel Search", position))
        variants.append(move_target_agent(confusing_seed, "Maya Birthday Dinner", position))
    for seed in (401, 402, 403):
        variants.append(shuffle_roster(reuse_seed, seed))
        variants.append(shuffle_roster(confusing_seed, seed))
    return all_cases() + tuple(variants)


validate_cases(all_cases())
