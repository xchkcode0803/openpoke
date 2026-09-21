"""Paired stress fixtures; ownership evidence is always visible to the agent."""

from dataclasses import replace
from itertools import product
from random import Random

from .base import RoutingCase, RoutingTurn, ExpectedDelegation, validate_cases


def stress_seeds() -> tuple[tuple[RoutingCase, str, tuple[str, ...]], ...]:
    return (
        (
            RoutingCase(
                name='reuses_original_email_agent_despite_similar_names',
                description="Maya's lease renewal email was found by Maya Lease Correspondence; that worker holds the original thread.",
                initial_agents=('Maya Lease Correspondence',),
                initial_conversation=(('poke_reply', "Maya's lease renewal email was found by Maya Lease Correspondence; that worker holds the original thread."),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message='Draft a reply to that lease renewal email asking for another week to decide. Do not send it.',
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='owner',
                                route='reuse',
                                acceptable_agent_names=('Maya Lease Correspondence',),
                                required_facts=('draft a reply on the original lease renewal thread asking for another week; do not send',),
                                max_calls=1,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Maya',
            ('Lease Payment', 'Lease Inspection', 'Lease Insurance'),
        ),
        (
            RoutingCase(
                name='selects_trip_agent_using_conversation_context',
                description='We are discussing lodging for the Montreal conference, handled by Montreal Conference Stay, not the family weekend.',
                initial_agents=('Montreal Conference Stay',),
                initial_conversation=(('poke_reply', 'We are discussing lodging for the Montreal conference, handled by Montreal Conference Stay, not the family weekend.'),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message='Ask for two cheaper places within walking distance of the conference venue.',
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='owner',
                                route='reuse',
                                acceptable_agent_names=('Montreal Conference Stay',),
                                required_facts=('two cheaper accommodations within walking distance of the conference venue',),
                                max_calls=1,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Montreal',
            ('Family Weekend', 'Restaurant Reservations', 'Flight Changes'),
        ),
        (
            RoutingCase(
                name='distinguishes_same_person_different_requests',
                description="Maya Dinner RSVP is waiting for Maya's response about dinner. Her cake order and apartment repairs are separate tasks.",
                initial_agents=('Maya Dinner RSVP',),
                initial_conversation=(('poke_reply', "Maya Dinner RSVP is waiting for Maya's response about dinner. Her cake order and apartment repairs are separate tasks."),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message='Check whether Maya accepted the dinner invitation.',
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='owner',
                                route='reuse',
                                acceptable_agent_names=('Maya Dinner RSVP',),
                                required_facts=('check whether Maya accepted the dinner invitation',),
                                max_calls=1,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Maya',
            ('Cake Order', 'Apartment Repairs', 'Lunch Invitation'),
        ),
        (
            RoutingCase(
                name='distinguishes_same_task_different_dates',
                description='The hotel options we are reviewing are for the November 2026 Montreal conference, owned by Montreal Conference Hotel November 2026.',
                initial_agents=('Montreal Conference Hotel November 2026',),
                initial_conversation=(('poke_reply', 'The hotel options we are reviewing are for the November 2026 Montreal conference, owned by Montreal Conference Hotel November 2026.'),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message='Ask for the cancellation terms for those hotel options.',
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='owner',
                                route='reuse',
                                acceptable_agent_names=('Montreal Conference Hotel November 2026',),
                                required_facts=('cancellation terms for the November 2026 Montreal conference hotel options',),
                                max_calls=1,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Montreal',
            ('Conference Hotel January', 'Conference Hotel February', 'Conference Hotel March'),
        ),
        (
            RoutingCase(
                name='prefers_context_owner_over_keyword_match',
                description="Apartment Move Logistics found the mover's quote email and holds the thread. Moving Quote Comparison is a separate task comparing public price lists.",
                initial_agents=('Apartment Move Logistics',),
                initial_conversation=(('poke_reply', "Apartment Move Logistics found the mover's quote email and holds the thread. Moving Quote Comparison is a separate task comparing public price lists."),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message="Draft a reply to the mover's quote asking whether packing is included. Don't send it.",
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='owner',
                                route='reuse',
                                acceptable_agent_names=('Apartment Move Logistics',),
                                required_facts=('draft a reply to the original mover quote asking whether packing is included; do not send',),
                                max_calls=1,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Moving',
            ('Quote Comparison', 'Packing Supply Prices', 'Van Rental Prices'),
        ),
        (
            RoutingCase(
                name='returns_to_previous_task_after_topic_changes',
                description="Kitchen Leak Repair Thread holds the landlord's kitchen leak email. Since then we discussed a gym cancellation and a dentist appointment, neither related to the repair.",
                initial_agents=('Kitchen Leak Repair Thread',),
                initial_conversation=(('poke_reply', "Kitchen Leak Repair Thread holds the landlord's kitchen leak email. Since then we discussed a gym cancellation and a dentist appointment, neither related to the repair."),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message="Back to the kitchen leak: draft a reply on the landlord's thread asking for a repair date, without sending it.",
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='owner',
                                route='reuse',
                                acceptable_agent_names=('Kitchen Leak Repair Thread',),
                                required_facts=('draft a reply on the landlord kitchen leak thread asking for a repair date; do not send',),
                                max_calls=1,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Kitchen',
            ('Renovation Quotes', 'Appliance Warranty', 'Cleaning Appointment'),
        ),
        (
            RoutingCase(
                name='routes_multiple_followups_to_their_existing_owners',
                description='Kitchen Leak Repair Thread owns the landlord repair thread. Gym Cancellation Thread owns the gym cancellation email; these are independent conversations.',
                initial_agents=('Kitchen Leak Repair Thread', 'Gym Cancellation Thread'),
                initial_conversation=(('poke_reply', 'Kitchen Leak Repair Thread owns the landlord repair thread. Gym Cancellation Thread owns the gym cancellation email; these are independent conversations.'),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message="Draft replies asking the landlord for a repair date and the gym for cancellation confirmation. Don't send either.",
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='owner',
                                route='reuse',
                                acceptable_agent_names=('Kitchen Leak Repair Thread',),
                                required_facts=('draft a reply asking the landlord for a repair date; do not send',),
                                max_calls=1,
                            ),
                            ExpectedDelegation(
                                task_key='gym',
                                route='reuse',
                                acceptable_agent_names=('Gym Cancellation Thread',),
                                required_facts=('draft a reply asking the gym for cancellation confirmation; do not send',),
                                max_calls=1,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Kitchen',
            ('Renovation Quotes', 'Appliance Warranty', 'Cleaning Appointment'),
        ),
        (
            RoutingCase(
                name='creates_agent_when_similar_names_have_different_purposes',
                description='Existing Montreal agents handle restaurant menus, museum tickets, and train fares. No existing task concerns accessibility information for libraries.',
                initial_agents=(),
                initial_conversation=(('poke_reply', 'Existing Montreal agents handle restaurant menus, museum tickets, and train fares. No existing task concerns accessibility information for libraries.'),),
                turns=(
                    RoutingTurn(
                        source='user',
                        message='Find wheelchair-accessible public libraries in Montreal and compare their weekend opening hours.',
                        expected_action='delegate',
                        delegations=(
                            ExpectedDelegation(
                                task_key='libraries',
                                route='create',
                                acceptable_agent_names=(),
                                required_facts=('find wheelchair-accessible Montreal public libraries and compare weekend hours',),
                                max_calls=None,
                            ),
                        ),
                    ),
                ),
                tags=frozenset({"stress", "development"}),
            ),
            'Montreal',
            ('Restaurant Menus', 'Museum Tickets', 'Train Fares'),
        ),
    )


def stress_cases() -> tuple[RoutingCase, ...]:
    result = []
    for index, (case, entity, purposes) in enumerate(stress_seeds()):
        # None of these purposes owns the requested continuation or the new library task.
        qualifiers = [f"{month} {year} — {person}" for year, month, person in product(range(2022, 2032), ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), ("Alex", "Sam", "Jordan", "Taylor", "Robin", "Casey", "Morgan", "Jamie", "Avery", "Riley", "Cameron", "Drew", "Quinn", "Blair", "Reese", "Rowan", "Skyler", "Hayden", "Parker", "Sage"))]
        similar = [f"{entity} {purpose} — {qualifier}" for purpose, qualifier in product(purposes, qualifiers)]
        unrelated = [f"{purpose} — {qualifier}" for purpose, qualifier in product(("Library Card Renewal", "Bicycle Maintenance", "Pet Vaccination", "Garden Supplies"), qualifiers)]
        rng = Random(8400 + index)
        rng.shuffle(similar)
        rng.shuffle(unrelated)
        distractors = tuple(value for pair in zip(similar, unrelated) for value in pair)
        for size in (10, 100, 1000):
            roster = distractors[:size - len(case.initial_agents)] + case.initial_agents
            result.append(replace(case, name=f"{case.name}__roster_{size}", initial_agents=roster, tags=case.tags | {f"roster_size_{size}"}))
    validate_cases(tuple(result))
    return tuple(result)
