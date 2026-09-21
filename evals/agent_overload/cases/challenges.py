"""Authored ownership evidence, independent of the production ranker."""
from dataclasses import dataclass
from .base import RoutingCase, user, reuse, create, validate_cases


@dataclass(frozen=True)
class Challenge:
    case: RoutingCase
    history: dict
    # A feasible discovery sequence, not a grading requirement.
    discovery: tuple[tuple[str, dict], ...]
    evidence: str


def challenges():
    result = []

    def add(name, description, names, message, owner, history=None, conversation=(), discovery=(), evidence='', extra=()):
        expected = reuse('owner', owner, required_facts=(message,)) if owner else create('new_work', message)
        case = RoutingCase(name=name, description=description, initial_agents=tuple(names),
            initial_conversation=tuple(conversation), turns=(user(message, 'delegate', expected, *extra),),
            tags=frozenset({'routing_challenge', 'stress'}))
        result.append(Challenge(case, history or {}, tuple(discovery), evidence or description))

    crowd = tuple(f'Montreal Visit {i:02d}' for i in range(1, 29))
    add('finds_owner_among_many_previously_mentioned_agents',
        'All visit owners are mentioned; the workshop identifier distinguishes the requested trip.',
        crowd + ('Montreal Aster Workshop',),
        'For the Aster workshop trip, ask the hotel for wheelchair access details.', 'Montreal Aster Workshop',
        conversation=(('poke_reply', 'Montreal Aster Workshop owns the Aster workshop hotel booking.'),
                      ('poke_reply', 'Other separate visits are being handled by: ' + ', '.join(crowd))),
        discovery=(('search_agents', {'query': 'Aster'}),))

    old_context = (('user_message', 'The travel desk calls my botanical retreat Fernhaven. Keep its existing hotel search going.'),)
    old_context += tuple(('poke_reply', f'Household update {i}: the garden supplies, bicycle service, library renewal, and pet appointment are separate tasks. No travel bookings changed. ' * 5) for i in range(10))
    add('recovers_owner_from_older_conversation_clues', 'An older non-name clue maps the retreat to Fernhaven.',
        ('Fernhaven Lodging', 'Botanical Garden Tickets'), 'Ask the hotel search for my botanical retreat about late checkout.',
        'Fernhaven Lodging', conversation=old_context, discovery=(('search_agents', {'query': 'Fernhaven'}),))

    add('finds_owner_when_request_uses_different_words', 'Earlier context supplies the service name used by the agent.',
        ('Westside Contract Termination', 'Exercise Equipment Returns'), 'Any progress on quitting the place where I work out?',
        'Westside Contract Termination', conversation=(('user_message', 'My fitness club is Westside. The cancellation is already being handled.'),),
        discovery=(('search_agents', {'query': 'Westside'}),))

    add('identifies_vaguely_named_owner_from_recorded_work', 'The notes label is searchable, but assignment evidence establishes ownership.',
        ('Notes Juniper', 'Notes Cedar', 'Apartment Renovation Estimates'), 'Continue the apartment deposit dispute and draft a follow-up; do not send it.',
        'Notes Juniper', history={'Notes Juniper': (('agent_request', 'Handle the apartment deposit dispute with the landlord.'),),
                                 'Notes Cedar': (('agent_request', 'Compare furniture delivery fees.'),)},
        conversation=(('user_message', 'I put the deposit dispute under one of my Notes labels, Juniper or Cedar.'),),
        discovery=(('search_agents', {'query': 'Notes'}), ('inspect_agent', {'agent_name': 'Notes Juniper'})))

    generic = ('agent_request', 'Continue the assigned travel correspondence; preserve the established booking reference.')
    add('uses_intermediate_assignment_to_identify_owner', 'Only an intermediate assignment connects the owner to booking Kestrel.',
        ('Travel Desk Amber', 'Travel Desk Indigo'), 'For booking Kestrel, ask whether breakfast is included.', 'Travel Desk Indigo',
        history={'Travel Desk Amber': (generic, ('agent_request', 'Handle booking Willow, unrelated to Kestrel.'), generic),
                 'Travel Desk Indigo': (generic, ('agent_request', 'Handle hotel booking Kestrel.'), generic)},
        conversation=(('user_message', 'The booking is with one of my Travel Desk agents.'),),
        discovery=(('search_agents', {'query': 'Travel Desk'}), ('inspect_agent', {'agent_name': 'Travel Desk Indigo'})),
        evidence='Handle hotel booking Kestrel.')

    add('uses_worker_response_to_identify_owner', 'The worker response identifies the booking; assignments do not.',
        ('Reservation Desk Maple', 'Reservation Desk Birch'), 'Ask the owner of booking RAVEN-72 to request late checkout.', 'Reservation Desk Birch',
        history={'Reservation Desk Maple': (generic, ('agent_response', 'My booking is FINCH-18.')),
                 'Reservation Desk Birch': (generic, ('agent_response', 'I secured hotel booking RAVEN-72.'))},
        conversation=(('user_message', 'The booking was made by one of the Reservation Desk agents.'),),
        discovery=(('search_agents', {'query': 'Reservation Desk'}), ('inspect_agent', {'agent_name': 'Reservation Desk Birch'})),
        evidence='I secured hotel booking RAVEN-72.')

    add('finds_ownership_evidence_on_older_history_page', 'The identifying response is behind six more recent eligible records.',
        ('Housing Desk Elm', 'Housing Desk Ash'), 'Continue the housing request for the private balcony and ask for viewing times.', 'Housing Desk Elm',
        history={'Housing Desk Elm': (('agent_request', 'Continue the assigned housing search.'), ('agent_response', 'This housing request requires a private balcony.')) +
                    tuple(('agent_response', f'Availability check {i}: awaiting replies.') for i in range(7)),
                 'Housing Desk Ash': (('agent_request', 'Continue the assigned housing search.'),
                                      ('agent_response', 'This housing request requires a shared garden, not a private balcony.'),
                                      ('agent_request', 'Continue the assigned housing search.'))},
        conversation=(('user_message', 'One of my Housing Desk agents handles that search.'),),
        discovery=(('search_agents', {'query': 'Housing Desk'}), ('inspect_agent', {'agent_name': 'Housing Desk Elm'}),
                   ('inspect_agent', {'agent_name': 'Housing Desk Elm', 'offset': 6})),
        evidence='This housing request requires a private balcony.')

    add('follows_explicit_handoff_to_current_owner', 'Recorded assignments explicitly transfer ownership, overriding the old descriptive name.',
        ('Lisbon Flight Search', 'Travel Followups Marigold'), 'Check whether my Lisbon flight can be changed without a fee.', 'Travel Followups Marigold',
        history={'Lisbon Flight Search': (('agent_request', 'Find Lisbon flights.'), ('agent_request', 'Transfer all Lisbon flight work to Travel Followups Marigold. Do not continue flight work here.')),
                 'Travel Followups Marigold': (('agent_request', 'Take over all Lisbon flight work from Lisbon Flight Search.'),)},
        conversation=(('poke_reply', 'Lisbon Flight Search originally handled this booking; its latest assignment records the handoff.'),),
        discovery=(('inspect_agent', {'agent_name': 'Lisbon Flight Search'}), ('search_agents', {'query': 'Marigold'})))

    add('distinguishes_recurring_tasks_by_specific_reference', 'A specific property and policy reference resolves repeated renewals.',
        ('Home Insurance Oak Lane 2026 PINE-24', 'Home Insurance Oak Lane 2026 PINE-42', 'Home Insurance Lake Road 2026 PINE-24'),
        'For Oak Lane policy PINE-42, ask for the renewal premium without changing coverage.', 'Home Insurance Oak Lane 2026 PINE-42',
        discovery=(('search_agents', {'query': 'Oak Lane PINE-42'}),))

    add('discovers_missing_owner_for_second_followup', 'Hotel ownership is explicit; parcel ownership requires following the carrier clue.',
        ('Oslo Hotel Booking', 'Northstar Parcel Claim') + tuple(f'Parcel Claim Ref {i:02d}' for i in range(24)), 'Ask my Oslo hotel for parking prices, and check the damaged parcel claim.', 'Oslo Hotel Booking',
        conversation=(('poke_reply', 'Oslo Hotel Booking owns the hotel reservation.'), ('user_message', 'Northstar is the carrier handling my damaged parcel; a claim agent is already working on it.'),
                      ('poke_reply', 'Other separate parcel claims are handled by: ' + ', '.join(f'Parcel Claim Ref {i:02d}' for i in range(24)))),
        discovery=(('search_agents', {'query': 'Northstar'}),),
        extra=(reuse('parcel', 'Northstar Parcel Claim', required_facts=('Check the damaged parcel claim.',)),))
    # Each owner receives only its own task clause.
    from dataclasses import replace
    item = result[-1]
    turn = item.case.turns[0]
    hotel = replace(turn.delegations[0], required_facts=('Ask the Oslo hotel for parking prices.',))
    result[-1] = replace(item, case=replace(item.case, turns=(replace(turn, delegations=(hotel, *turn.delegations[1:])),)))

    add('refines_search_after_plausible_wrong_matches', 'The generic storage query points at household tasks; context supplies the service name.',
        ('Boxroom Subscription Closure', 'Storage Unit Rent', 'Storage Furniture Quotes'), 'Follow up on cancelling my online storage subscription.',
        'Boxroom Subscription Closure', conversation=(('user_message', 'My online file storage service is Boxroom. Cancellation is already in progress.'),),
        discovery=(('search_agents', {'query': 'storage'}), ('search_agents', {'query': 'Boxroom'})))

    add('creates_agent_when_similar_agents_own_different_work', 'Known renewal and billing agents do not own the explicitly new complaint.',
        ('Internet Renewal', 'Internet Billing Review'), 'Start a new, separate complaint about internet outages; do not change my renewal or billing work.', None,
        history={'Internet Renewal': (('agent_request', 'Compare renewal prices only; outage complaints are separate work.'),),
                 'Internet Billing Review': (('agent_request', 'Check invoice arithmetic only; outage complaints are separate work.'),)},
        discovery=(('search_agents', {'query': 'Internet'}),))
    validate_cases(tuple(item.case for item in result))
    return tuple(result)
