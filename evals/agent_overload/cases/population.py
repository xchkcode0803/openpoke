"""Versioned synthetic populations; large rosters are built only during execution."""
import hashlib
from dataclasses import dataclass, replace
from .stress import stress_seeds
from .challenges import challenges

VERSION = 'clustered_personal_tasks_v1'
SCALE_SIZES = (10, 100, 1000, 10_000, 100_000, 1_000_000)
CHALLENGE_SIZES = (100, 10_000, 1_000_000)
CHALLENGE_TOPICS = (
    ('Montreal', 'Workshop', 'Hotel'), ('Botanical', 'Retreat', 'Hotel'),
    ('Fitness', 'Contract', 'Cancellation'), ('Apartment', 'Deposit', 'Notes'),
    ('Travel', 'Booking', 'Breakfast'), ('Reservation', 'Hotel', 'Checkout'),
    ('Housing', 'Balcony', 'Viewing'), ('Lisbon', 'Flight', 'Travel'),
    ('Oak Lane', 'Insurance', 'Renewal'), ('Oslo', 'Hotel', 'Parcel'),
    ('Storage', 'Subscription', 'Cancellation'), ('Internet', 'Billing', 'Renewal'),
)
PEOPLE = ('Maya', 'Alex', 'Sam', 'Robin', 'Casey', 'Morgan', 'Jamie', 'Avery', 'Quinn', 'Rowan', 'Taylor', 'Drew')
PLACES = ('Montreal', 'Lisbon', 'Oslo', 'Toronto', 'Oak Lane', 'Lake Road', 'Westside', 'Brookfield')
FAMILIES = ('Travel insurance', 'Housing inspection', 'Appointment scheduling', 'Invoice review',
            'Purchase return', 'Repair estimate', 'Event catering', 'Membership renewal', 'Correspondence archive')


@dataclass(frozen=True)
class Variant:
    kind: str
    index: int
    size: int

    @property
    def key(self):
        return f'{self.kind}_{self.index:02d}_{self.size}'

    @property
    def seed(self):
        return 9137 + self.index * 101 + (10000 if self.kind == 'challenge' else 0)

    def source(self):
        if self.kind == 'scale':
            case, entity, purposes = stress_seeds()[self.index]
            return case, {}, entity, purposes
        challenge = challenges()[self.index]
        # References make background tasks explicitly distinct from authored work.
        return challenge.case, challenge.history, 'Personal', FAMILIES


SCALE_VARIANTS = tuple(Variant('scale', i, size) for size in SCALE_SIZES for i in range(8))
CHALLENGE_VARIANTS = tuple(Variant('challenge', i, size) for size in CHALLENGE_SIZES for i in range(12))


def reference(number):
    """Stable account/reservation reference, not a unique answer-bearing suffix."""
    letters = ''
    while True:
        number, digit = divmod(number, 26)
        letters = chr(65 + digit) + letters
        if not number:
            return letters


def background_name(index, seed, entity, purposes, related_terms=()):
    value = index + seed
    person = PEOPLE[value % len(PEOPLE)]
    place = PLACES[(value // 7) % len(PLACES)]
    year = 2022 + value % 9
    month = 1 + (value // 11) % 12
    ref = reference(value)
    if index % 2 == 0:
        purpose = purposes[(value // 3) % len(purposes)]
        topic = related_terms[(value // 5) % len(related_terms)] if related_terms else entity
    else:
        purpose = FAMILIES[(value // 3) % len(FAMILIES)]
        topic = place
    # Each style retains a distinct task reference; no background task is the
    # authored booking/property/claim. Style selection is independent of owners.
    styles = (
        f'{topic} {purpose} — {person}, {year}-{month:02d}, ref {ref}',
        f'{person}: {topic} / {purpose.lower()} / account {ref}',
        f'{purpose.upper()} ({topic}) — {ref} — {year}',
        f'{topic} stuff: {purpose.lower()}, reservation {ref}',
        f'{person} {purpose.lower()} follow-up — {topic} {ref}',
        f'{year} records / {topic} / {purpose} / {ref}',
    )
    return styles[value % len(styles)]


def materialize(variant):
    case, history, entity, purposes = variant.source()
    related_terms = CHALLENGE_TOPICS[variant.index] if variant.kind == 'challenge' else ()
    critical = set(case.initial_agents)
    names = []
    index = 0
    while len(names) < variant.size - len(critical):
        name = background_name(index, variant.seed, entity, purposes, related_terms)
        index += 1
        if name not in critical:
            names.append(name)
    names.extend(case.initial_agents)
    roster = tuple(names)
    digest = hashlib.sha256()
    for name in roster:
        digest.update(name.encode('utf-8') + b'\n')
    case = replace(case, name=f'{case.name}__{variant.key}', initial_agents=roster,
                   tags=frozenset({'stress', f'routing_{variant.kind}'}))
    metadata = {'variant': variant.key, 'generator': VERSION, 'seed': variant.seed,
                'roster_size': len(roster), 'roster_sha256': digest.hexdigest(),
                'scenario': variant.source()[0].name}
    return case, history, metadata


def specifications():
    return [{'kind': v.kind, 'index': v.index, 'size': v.size, 'seed': v.seed,
             'scenario': v.source()[0].name} for v in SCALE_VARIANTS + CHALLENGE_VARIANTS]
