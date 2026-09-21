"""Additional history fixtures; the original baseline case definitions stay frozen."""
from .base import RoutingCase, RoutingTurn, reuse, validate_cases


INSPECTION_CASES = (
    RoutingCase(
        name='finds_maya_dinner_owner_from_assignments',
        description='Two Maya agents have different assignments recorded in their histories.',
        initial_agents=('Maya Planning A', 'Maya Planning B'), initial_conversation=(),
        turns=(RoutingTurn('user', "Continue Maya's birthday dinner booking and find a vegetarian menu.", 'delegate',
            (reuse('dinner', 'Maya Planning B', required_facts=('Find a vegetarian menu for Maya’s birthday dinner.',)),)),),
        tags=frozenset({'inspection'})),
    RoutingCase(
        name='finds_montreal_owner_from_previous_work',
        description='Trip names alone do not identify which one has the conference booking.',
        initial_agents=('Montreal Trip A', 'Montreal Trip B'), initial_conversation=(),
        turns=(RoutingTurn('user', 'Ask the hotel from my Montreal conference trip for late checkout.', 'delegate',
            (reuse('checkout', 'Montreal Trip A', required_facts=('Request late checkout for the Montreal conference hotel.',)),)),),
        tags=frozenset({'inspection'})),
    RoutingCase(
        name='finds_original_assignment_on_older_page',
        description='The original balcony requirement is older than six generic follow-up entries.',
        initial_agents=('Apartment Search A', 'Apartment Search B'), initial_conversation=(),
        turns=(RoutingTurn('user', 'Continue the apartment search that required a private balcony. Ask for viewing times.', 'delegate',
            (reuse('viewings', 'Apartment Search A', required_facts=('Ask for viewing times for the private-balcony apartment search.',)),)),),
        tags=frozenset({'inspection'})),
    RoutingCase(
        name='reuses_known_owner_without_recorded_history',
        description='Main conversation establishes the owner even though its execution log is empty.',
        initial_agents=('Dental Appointment',),
        initial_conversation=(('poke_reply', 'Dental Appointment is handling your checkup booking.'),),
        turns=(RoutingTurn('user', 'Ask them for a morning slot instead.', 'delegate',
            (reuse('dental', 'Dental Appointment', required_facts=('Request a morning checkup slot.',)),)),),
        tags=frozenset({'inspection'})),
    RoutingCase(
        name='uses_updated_assignment_scope',
        description='The latest assignments explicitly transfer the flight task to a different owner.',
        initial_agents=('Lisbon Travel A', 'Lisbon Travel B'), initial_conversation=(),
        turns=(RoutingTurn('user', 'Continue my Lisbon flight search and check for a direct flight.', 'delegate',
            (reuse('flights', 'Lisbon Travel B', required_facts=('Check for a direct Lisbon flight.',)),)),),
        tags=frozenset({'inspection'})),
    RoutingCase(
        name='routes_two_followups_using_recorded_owners',
        description='Two Toronto planning histories establish hotel and restaurant ownership.',
        initial_agents=('Toronto Planning A', 'Toronto Planning B'), initial_conversation=(),
        turns=(RoutingTurn('user', 'For my Toronto trip, ask the hotel for parking prices and the restaurant for vegetarian options.', 'delegate', (
            reuse('parking', 'Toronto Planning A', required_facts=('Ask the Toronto hotel for parking prices.',)),
            reuse('menu', 'Toronto Planning B', required_facts=('Ask the Toronto restaurant for vegetarian options.',)),)),),
        tags=frozenset({'inspection'})),
)

INSPECTION_HISTORY = {
    'finds_maya_dinner_owner_from_assignments': {
        'Maya Planning A': (('agent_request', 'Arrange Maya’s dentist appointment.'),),
        'Maya Planning B': (('agent_request', 'Book Maya’s birthday dinner at an Italian restaurant.'),)},
    'finds_montreal_owner_from_previous_work': {
        'Montreal Trip A': (('agent_request', 'Book the hotel for my Montreal conference trip.'),
                           ('agent_response', 'The conference booking is at Hotel Bonaventure.')),
        'Montreal Trip B': (('agent_request', 'Plan a Montreal family museum weekend.'),)},
    'finds_original_assignment_on_older_page': {
        'Apartment Search A': (('agent_request', 'Find an apartment with a private balcony.'),) +
            tuple(('agent_response', f'Follow-up {i}: still awaiting availability.') for i in range(6)),
        'Apartment Search B': (('agent_request', 'Find a ground-floor apartment with a private garden; no balcony needed.'),)},
    'reuses_known_owner_without_recorded_history': {},
    'uses_updated_assignment_scope': {
        'Lisbon Travel A': (('agent_request', 'Find Lisbon flights.'),
                           ('agent_request', 'Flight work is now owned by Lisbon Travel B. You handle hotels only.')),
        'Lisbon Travel B': (('agent_request', 'Find Lisbon hotels.'),
                           ('agent_request', 'Take over the Lisbon flight search from Lisbon Travel A. You now own flights.'))},
    'routes_two_followups_using_recorded_owners': {
        'Toronto Planning A': (('agent_request', 'Book a Toronto hotel near the station.'),),
        'Toronto Planning B': (('agent_request', 'Reserve dinner at a Toronto restaurant.'),)},
}

validate_cases(INSPECTION_CASES)
