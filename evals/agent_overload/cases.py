"""Hand-authored routing scenarios and deterministic roster variants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random
from typing import Literal


TurnSource = Literal["user", "execution_agent"]
ExpectedAction = Literal["delegate", "respond", "wait"]
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
    min_calls: int = 1
    max_calls: int | None = 1


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
    min_calls: int = 1,
    max_calls: int | None = 1,
) -> ExpectedDelegation:
    return ExpectedDelegation(
        task_key=task_key,
        route="reuse",
        acceptable_agent_names=agent_names,
        required_facts=required_facts,
        forbidden_facts=forbidden_facts,
        agent_from_task=agent_from_task,
        min_calls=min_calls,
        max_calls=max_calls,
    )


def create(
    task_key: str,
    *required_facts: str,
    forbidden_facts: tuple[str, ...] = (),
    min_calls: int = 1,
    max_calls: int | None = 1,
) -> ExpectedDelegation:
    return ExpectedDelegation(
        task_key=task_key,
        route="create",
        required_facts=required_facts,
        forbidden_facts=forbidden_facts,
        min_calls=min_calls,
        max_calls=max_calls,
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
            user("Plan Maya's birthday dinner in Toronto next Saturday at 7 PM for six people. Budget up to $100 per person, Italian food, and no shellfish. Find restaurant options and help coordinate the reservation.", "delegate", create("maya_dinner", "plan Maya's Toronto birthday dinner next Saturday at 7 PM for six people", "keep the budget at or below $100 per person", "find Italian options with no shellfish and help coordinate the reservation")),
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
        "requests_details_after_incomplete_worker_update",
        "Reuses the reporting worker when its result omits the useful details.",
        ("Montreal Hotel Search",),
        (worker("[SUCCESS] Montreal Hotel Search: I found three hotels near Old Montreal.", "delegate", reuse("hotel_details", "Montreal Hotel Search", required_facts=("provide the three hotel names and details",))),),
        "development", "worker_update", "smoke", "semantic",
    ),
    # Execution-agent updates: 3
    _case(
        "reports_completed_worker_update_without_redelegating",
        "Reports a completed worker result without restarting the task.",
        ("Montreal Hotel Search",),
        (worker("[SUCCESS] Montreal Hotel Search: Hotel Nelligan is $290 per night, Le Petit Hotel is $245 per night, and William Gray is $320 per night. All three are near Old Montreal.", "respond", response_requirements=("report the three named hotels and their prices",)),),
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
        "Uses the explicitly requested tax year rather than an older filing.",
        ("2025 Tax Documents", "2026 Tax Documents"),
        (user("Continue my filing for the 2026 tax year.", "delegate", reuse("taxes", "2026 Tax Documents", required_facts=("continue the 2026 tax filing",))),),
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
        "creates_related_agents_when_existing_travel_agents_do_not_fit",
        "Creates one or more relevant relocation workers instead of reusing travel agents.",
        ("Montreal Hotel Search", "Montreal Flight Search", "Montreal Restaurant Reservations"),
        (user("Research whether I should move to Montreal permanently.", "delegate", create("montreal_move", "research moving to Montreal permanently", min_calls=1, max_calls=None)),),
        "development", "negative", "smoke", "semantic",
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
            flexible_groups = 0
            if turn.expected_action == "delegate" and not turn.delegations:
                raise ValueError(f"delegation expected without targets: {case.name}")
            if turn.expected_action != "delegate" and turn.delegations:
                raise ValueError(f"delegations on non-routing turn: {case.name}")
            for expected in turn.delegations:
                if expected.route == "reuse" and not (expected.acceptable_agent_names or expected.agent_from_task):
                    raise ValueError(f"reuse expectation has no target: {case.name}")
                if expected.route == "reuse" and not expected.agent_from_task:
                    missing = set(expected.acceptable_agent_names) - set(case.initial_agents)
                    if missing:
                        raise ValueError(
                            f"reuse targets are absent from roster in {case.name}: {sorted(missing)}"
                        )
                if expected.route == "create":
                    created_tasks.add(expected.task_key)
                if expected.agent_from_task and expected.agent_from_task not in created_tasks:
                    raise ValueError(f"unknown created-agent reference: {case.name}")
                if expected.min_calls < 1:
                    raise ValueError(f"delegation minimum must be positive: {case.name}")
                if expected.max_calls is not None and expected.max_calls < expected.min_calls:
                    raise ValueError(f"delegation range is invalid: {case.name}")
                if expected.max_calls is None or expected.max_calls > 1:
                    flexible_groups += 1
                    if expected.agent_from_task:
                        raise ValueError(f"dynamic reuse cannot be flexible: {case.name}")
            if flexible_groups > 1:
                raise ValueError(f"only one flexible delegation group is allowed: {case.name}")


_UNRELATED_TASKS = (
    "Renew Library Card",
    "Cancel Gym Membership",
    "Schedule Dentist Appointment",
    "Find Electricity Receipt",
    "Compare Coffee Grinders",
    "Replace Apartment Air Filter",
    "Review Mobile Phone Plan",
    "Refill Prescription",
    "Update Car Insurance",
    "Repair Laptop",
    "Order Plant Delivery",
    "Track Package Delivery",
    "Organize Tax Documents",
    "Compare Standing Desks",
    "Schedule Annual Eye Exam",
    "Return Running Shoes",
    "Review Streaming Subscriptions",
    "Book Haircut",
    "Prepare Grocery List",
    "Replace Smoke Detector",
    "Check Water Bill",
    "Service Bicycle",
    "Arrange Pet Vaccination",
    "Review Bank Fees",
)

_TASK_QUALIFIERS = tuple(
    [f"{month} {year}" for year in range(2024, 2028) for month in (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )]
    + ["for Jordan", "for Elena", "for Parents", "for Apartment 2B"]
)

_HOTEL_NEIGHBOR_TASKS = (
    "Cancel Montreal Hotel Reservation",
    "Request Montreal Hotel Refund",
    "Find Montreal Hotel Receipt",
    "Review Montreal Hotel Charges",
    "Resolve Montreal Hotel Complaint",
    "Change Montreal Hotel Dates",
    "Check Montreal Hotel Loyalty Points",
    "Arrange Montreal Hotel Accessibility",
    "Coordinate Montreal Hotel Group Booking",
    "Request Montreal Hotel Invoice",
    "Toronto Hotel Search",
    "Quebec City Hotel Search",
    "Boston Hotel Search",
    "Ottawa Hotel Search",
    "Chicago Hotel Search",
)

_MAYA_NEIGHBOR_TASKS = (
    "Email Maya About Apartment",
    "Maya Birthday Gift",
    "Maya Conference Travel",
    "Maya Dinner Receipt",
    "Maya Dinner Photos",
    "Cancel Maya Restaurant Reservation",
    "Maya Dietary Preferences",
    "Maya Lunch Coordination",
    "Maya Birthday Cake",
    "Maya Event Invitations",
    "Maya Expense Reimbursement",
    "Maya Project Follow-up",
)


def _unrelated_candidates() -> list[str]:
    return [f"{task} — {qualifier}" for task in _UNRELATED_TASKS for qualifier in _TASK_QUALIFIERS]


def _similar_candidates(target_name: str) -> list[str]:
    if target_name == "Montreal Hotel Search":
        tasks = _HOTEL_NEIGHBOR_TASKS
    elif target_name == "Maya Birthday Dinner":
        tasks = _MAYA_NEIGHBOR_TASKS
    else:
        raise ValueError(f"no realistic neighbor pool for target: {target_name}")
    return [f"{task} — {qualifier}" for task in tasks for qualifier in _TASK_QUALIFIERS]


def scale_roster_with_unrelated_agents(case: RoutingCase, total_size: int, seed: int) -> RoutingCase:
    if total_size < len(case.initial_agents):
        raise ValueError("total roster size cannot be smaller than the authored roster")
    rng = Random(seed)
    candidates = _unrelated_candidates()
    rng.shuffle(candidates)
    available = [name for name in candidates if name not in case.initial_agents]
    needed = total_size - len(case.initial_agents)
    if len(available) < needed:
        raise ValueError(f"not enough unrelated agents for roster size {total_size}")
    return replace(
        case,
        name=f"{case.name}__roster_{total_size}_unrelated_seed_{seed}",
        initial_agents=case.initial_agents + tuple(available[:needed]),
        tags=case.tags | frozenset({"overload", f"roster_size_{total_size}", "unrelated_growth"}),
    )


def add_similar_agents(
    case: RoutingCase,
    target_name: str,
    count: int,
    seed: int,
    total_size: int = 500,
) -> RoutingCase:
    if target_name not in case.initial_agents:
        raise ValueError(f"target is absent from roster: {target_name}")
    if count > total_size - len(case.initial_agents):
        raise ValueError("similar-agent count does not fit in requested roster size")
    rng = Random(seed)
    similar = _similar_candidates(target_name)
    rng.shuffle(similar)
    selected_similar = [name for name in similar if name not in case.initial_agents][:count]
    if len(selected_similar) < count:
        raise ValueError(f"not enough similar agents for density {count}")
    unrelated = _unrelated_candidates()
    rng.shuffle(unrelated)
    used = set(case.initial_agents) | set(selected_similar)
    unrelated_needed = total_size - len(case.initial_agents) - len(selected_similar)
    selected_unrelated = [name for name in unrelated if name not in used][:unrelated_needed]
    if len(selected_unrelated) < unrelated_needed:
        raise ValueError(f"not enough filler agents for roster size {total_size}")
    return replace(
        case,
        name=f"{case.name}__roster_{total_size}_similar_{count}_seed_{seed}",
        initial_agents=case.initial_agents + tuple(selected_similar) + tuple(selected_unrelated),
        tags=case.tags | frozenset({
            "overload", "similar_agents", f"roster_size_{total_size}", f"similar_count_{count}",
        }),
    )


def move_target_agent(case: RoutingCase, target_name: str, position: Literal["first", "middle", "last"]) -> RoutingCase:
    if target_name not in case.initial_agents:
        raise ValueError(f"target is absent from roster: {target_name}")
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
        "requests_details_after_incomplete_worker_update",
        "reports_completed_worker_update_without_redelegating",
        "distinguishes_same_person_different_tasks",
        "creates_related_agents_when_existing_travel_agents_do_not_fit",
        "routes_existing_and_new_task",
    }
    authored = tuple(case for case in DEVELOPMENT_CASES if case.name in names)
    result = authored + (
        scale_roster_with_unrelated_agents(_named_case("reuses_existing_hotel_search_agent"), 100, 11),
        scale_roster_with_unrelated_agents(_named_case("creates_related_agents_when_existing_travel_agents_do_not_fit"), 100, 13),
    )
    validate_cases(result)
    return result


def standard_cases() -> tuple[RoutingCase, ...]:
    representative = (
        _named_case("reuses_existing_hotel_search_agent"),
        _named_case("creates_related_agents_when_existing_travel_agents_do_not_fit"),
        _named_case("uses_conversation_to_resolve_pronoun"),
        _named_case("routes_two_existing_tasks") if any(case.name == "routes_two_existing_tasks" for case in DEVELOPMENT_CASES) else _named_case("selects_agent_from_unrelated_roster"),
    )
    result = DEVELOPMENT_CASES + tuple(
        scale_roster_with_unrelated_agents(case, 100, 20 + index)
        for index, case in enumerate(representative)
    )
    validate_cases(result)
    return result


def full_cases() -> tuple[RoutingCase, ...]:
    reuse_seed = _named_case("reuses_existing_hotel_search_agent")
    create_seed = _named_case("creates_related_agents_when_existing_travel_agents_do_not_fit")
    context_seed = _named_case("uses_conversation_to_resolve_pronoun")
    confusing_seed = _named_case("distinguishes_same_person_different_tasks")
    variants: list[RoutingCase] = []
    for seed_index, seed_case in enumerate((reuse_seed, create_seed, context_seed, confusing_seed)):
        for size in (10, 50, 100, 250, 500, 1000):
            variants.append(scale_roster_with_unrelated_agents(seed_case, size, 100 + seed_index * 10 + size))
    for count in (5, 25, 100, 250):
        variants.append(add_similar_agents(reuse_seed, "Montreal Hotel Search", count, 200 + count))
        variants.append(add_similar_agents(confusing_seed, "Maya Birthday Dinner", count, 300 + count))
    hard_reuse = add_similar_agents(reuse_seed, "Montreal Hotel Search", 100, 501)
    hard_confusing = add_similar_agents(confusing_seed, "Maya Birthday Dinner", 100, 503)
    for position in ("first", "middle", "last"):
        variants.append(move_target_agent(hard_reuse, "Montreal Hotel Search", position))
        variants.append(move_target_agent(hard_confusing, "Maya Birthday Dinner", position))
    for seed in (401, 402, 403):
        variants.append(shuffle_roster(hard_reuse, seed))
        variants.append(shuffle_roster(hard_confusing, seed))
    result = all_cases() + tuple(variants)
    validate_cases(result)
    return result


validate_cases(all_cases())
