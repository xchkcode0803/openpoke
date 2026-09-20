"""Durable, fail-closed reservations for one sequential evaluation campaign."""
import fcntl
import json
import math
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4


class BudgetStopped(RuntimeError):
    pass


class CampaignBudget:
    def __init__(self, directory, cap=10, case_name=None):
        self.case_name = case_name
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.cap = min(Decimal(str(cap)), Decimal('10'))
        if not self.cap.is_finite() or self.cap <= 0:
            raise ValueError('Campaign cap must be positive')
        self.path = self.directory / 'spend.json'
        self.prices = json.loads((self.directory / 'prices.json').read_text())

    @contextmanager
    def ledger(self):
        with (self.directory / 'spend.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text()) if self.path.exists() else {'requests': [], 'stopped': None}
            try:
                yield state
            finally:
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(state, indent=2))
                temporary.replace(self.path)

    def reserve(self, payload):
        model = payload['model']
        price = self.prices.get(model)
        if not price:
            raise BudgetStopped(f'Pricing unavailable for {model}')
        if 'questions' in payload:
            # Decisions may evaluate questions separately. Reserve a full context
            # per question, exceeding the submitted-state token estimate.
            inputs = int(price['context_length']) * max(1, len(payload['questions']))
            outputs = 0
        else:
            inputs = len(json.dumps(payload, ensure_ascii=False).encode()) + 4096
            outputs = payload.get('max_tokens') or price['max_completion_tokens']
        maximum = Decimal(str(price['prompt'])) * inputs + Decimal(str(price['completion'])) * outputs
        maximum += Decimal(str(price.get('request', 0)))
        if not maximum.is_finite() or maximum < 0:
            raise BudgetStopped('Pricing unavailable: invalid reservation')
        identifier = uuid4().hex
        with self.ledger() as state:
            if state['stopped']:
                raise BudgetStopped(state['stopped'])
            if any(row['status'] == 'reserved' for row in state['requests']):
                raise BudgetStopped('Unsettled request: reconcile provider usage before resuming')
            committed = sum(Decimal(str(row['charged'])) for row in state['requests'])
            if committed + maximum > self.cap:
                raise BudgetStopped(f'Budget limit: {committed} committed + {maximum} reservation exceeds {self.cap}')
            not_before = max(time.time(), state.get('next_request_at', 0))
            from .provider import request_interval
            state['next_request_at'] = not_before + request_interval()
            state['requests'].append({'case': self.case_name, 'not_before': not_before, 'id': identifier, 'model': model, 'reserved': str(maximum),
                                      'charged': str(maximum), 'status': 'reserved'})
        return identifier

    def delay(self, identifier):
        with self.ledger() as state:
            row = next(item for item in state["requests"] if item["id"] == identifier)
            return max(0, row["not_before"] - time.time())

    def settle(self, identifier, response):
        with self.ledger() as state:
            row = next(item for item in state['requests'] if item['id'] == identifier)
            if row['status'] != 'reserved':
                raise BudgetStopped('Request already settled')
            row['http_status'] = response.status_code
            # An explicit 429 rejects the request before generation. Other failed
            # or malformed responses remain conservatively reserved and stop runs.
            if response.status_code == 429:
                row.update(status='rate_limited', charged='0')
                return
            if response.status_code == 402:
                row.update(status='payment_rejected', charged='0')
                state['stopped'] = 'OpenRouter rejected the request before generation: restore account/key spending capacity'
                raise BudgetStopped(state['stopped'])
            try:
                payload = response.json()
                usage = payload.get('usage') or {}
                cost = usage.get('cost', payload.get('cost'))
                if cost is None or not math.isfinite(float(cost)) or float(cost) < 0:
                    raise ValueError('Missing or invalid provider charge')
                if not usage:
                    raise ValueError('Provider usage unavailable')
                charge = Decimal(str(cost))
                if charge > Decimal(row['reserved']):
                    row.update(status='over_reservation', charged=str(charge), usage=usage)
                    state['stopped'] = 'Provider charge exceeded conservative reservation'
                    raise BudgetStopped(state['stopped'])
            except (ValueError, TypeError, AttributeError) as exc:
                row['status'] = 'unresolved'
                state['stopped'] = str(exc)
                raise BudgetStopped(str(exc)) from exc
            row.update(status='settled', charged=str(charge), usage=usage)


def initialize_prices(directory, models=None):
    """Snapshot current public endpoint prices, including the highest price tier."""
    import httpx
    from datetime import datetime, timezone
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prices = {}
    raw = {}
    for model in dict.fromkeys(models or ('anthropic/claude-sonnet-4', 'typesafe/jev-1.13')):
        response = httpx.get(f'https://openrouter.ai/api/v1/models/{model}/endpoints', timeout=60)
        response.raise_for_status()
        raw[model] = response.json()
        endpoints = raw[model]['data']['endpoints']
        active = [endpoint for endpoint in endpoints if endpoint.get('status') == 0]
        if not active:
            raise BudgetStopped(f'Pricing unavailable for {model}')
        tiers = [tier for endpoint in active for tier in [endpoint['pricing'], *endpoint['pricing'].get('overrides', [])]]
        prices[model] = {
            'prompt': str(max(Decimal(tier['prompt']) for tier in tiers)),
            'completion': str(max(Decimal(tier['completion']) for tier in tiers)),
            'request': str(max(Decimal(tier.get('request', '0')) for tier in tiers)),
            'max_completion_tokens': max(endpoint.get('max_completion_tokens') or endpoint['context_length'] for endpoint in active),
            'context_length': min(endpoint['context_length'] for endpoint in active),
        }
    (directory / 'prices.json').write_text(json.dumps(prices, indent=2))
    (directory / 'pricing_evidence.json').write_text(json.dumps({'verified_at': datetime.now(timezone.utc).isoformat(), 'endpoints': raw}, indent=2))
