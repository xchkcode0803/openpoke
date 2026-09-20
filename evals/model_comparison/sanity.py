"""Three focused live checks of the two roles outside routing/Gmail coverage."""
import argparse
import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from .run import MODELS


async def check(root, output):
    from evals.agent_gmail.config import EvalConfig
    from evals.agent_gmail.provider import Provider
    from evals.agent_overload.harness import _reset_services
    from server.config import get_settings
    from server.services.gmail.processing import ProcessedEmail
    summary = importlib.import_module('server.services.conversation.summarization.summarizer')
    classifier = importlib.import_module('server.services.gmail.importance_classifier')
    _, conversation, memory, _ = _reset_services(root)
    model = MODELS['gemini']
    provider = Provider(EvalConfig(model, model, model, budget=1))
    await provider.verify()
    settings = get_settings().model_copy(update={
        'summarizer_model': model, 'email_classifier_model': model,
        'openrouter_api_key': 'provided-at-transport-boundary', 'summarization_enabled': True,
        'conversation_summary_threshold': 2, 'conversation_summary_tail_size': 0})
    traces = []
    def completion(role):
        async def call(**kwargs):
            kwargs.pop('api_key', None)
            result = await provider(role=role, **kwargs)
            traces.append({'role': role, 'request': kwargs, 'response': result})
            return result
        return call
    conversation.record_user_message('On 2026-09-25 at 14:00, Alice reviews the Cedar launch. Draft an email to alice@example.com with reference CEDAR-42. Do not send until I approve.')
    conversation.record_reply('The draft is prepared and is awaiting your approval. Nothing has been sent.')
    checks = []
    with ExitStack() as stack:
        for module in (summary, classifier):
            stack.enter_context(patch.object(module, 'get_settings', return_value=settings))
        stack.enter_context(patch.object(summary, '_resolve_conversation_log', return_value=conversation))
        stack.enter_context(patch.object(summary, 'get_working_memory_log', return_value=memory))
        stack.enter_context(patch.object(summary, 'request_chat_completion', completion('summarizer')))
        stack.enter_context(patch.object(classifier, 'request_chat_completion', completion('classifier')))
        completed = await summary.summarize_conversation()
        text = memory.load_summary_state().summary_text
        required = ('2026-09-25', '14:00', 'Alice', 'Cedar', 'CEDAR-42', 'alice@example.com')
        checks.append({'name': 'summary_preserves_facts', 'passed': completed and all(v in text for v in required), 'output': text,
                       'review_required': 'Check approval remains pending and no invented completed send.'})
        for name, subject, body, expected in (
            ('otp', 'Your login code', 'Your login code is 482913. It expires in 5 minutes.', True),
            ('marketing', 'Weekly store newsletter', 'Our weekly catalogue is here. Browse our new colours whenever you like.', False),
        ):
            email = ProcessedEmail(name, name, '', subject, 'notices@example.com', 'user@example.com',
                datetime(2026, 9, 20, tzinfo=timezone.utc), ['INBOX'], body, False, 0, [])
            value = await classifier.classify_email_importance(email)
            calls = traces[-1]['response'].get('choices', [{}])[0].get('message', {}).get('tool_calls', [])
            decisions = [json.loads(c['function']['arguments']) for c in calls if c['function']['name'] == 'mark_email_importance']
            passed = bool(decisions) and decisions[-1].get('important') is expected and (bool(value) is expected)
            checks.append({'name': name, 'passed': passed, 'output': value, 'decisions': decisions})
    result = {'model': model, 'checks': checks, 'traces': traces, 'provider_calls': provider.calls,
              'cost': provider.known_cost if not provider.cost_unknown else None}
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps({'checks': checks, 'cost': result['cost']}, indent=2))
    return int(not all(c['passed'] for c in checks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.deepeval/comparison-main-v1/gemini/role-sanity.json'))
    args = parser.parse_args()
    if os.getenv('RUN_LIVE_EVALS') != '1' or args.output.exists():
        parser.error('Requires RUN_LIVE_EVALS=1 and a new output file')
    from evals.agent_gmail.run import load_credentials
    load_credentials()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='roles-sanity-') as directory:
        with patch.dict(os.environ, {'OPENPOKE_DATA_DIR': directory}):
            return asyncio.run(check(Path(directory), args.output))


if __name__ == '__main__':
    raise SystemExit(main())
