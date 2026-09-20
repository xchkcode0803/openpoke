import asyncio
import json

from .sanity import check


def test_real_summary_and_classifier_paths_are_isolated(tmp_path, monkeypatch):
    from evals.agent_gmail.provider import Provider
    requested = []
    async def verify(self):
        pass
    async def completion(self, *, role, model, **kwargs):
        requested.append((role, model))
        if role == 'summarizer':
            message = {'content': '2026-09-25 14:00 Alice reviews Cedar, CEDAR-42, alice@example.com. Draft awaiting approval; do not send.'}
        else:
            important = '482913' in str(kwargs['messages'])
            message = {'tool_calls': [{'function': {'name': 'mark_email_importance',
                'arguments': json.dumps({'important': important, 'summary': 'Login code 482913 expires in 5 minutes.' if important else None})}}]}
        return {'choices': [{'message': message}]}
    monkeypatch.setattr(Provider, 'verify', verify)
    monkeypatch.setattr(Provider, '__call__', completion)
    output = tmp_path / 'result.json'
    assert asyncio.run(check(tmp_path, output)) == 0
    assert [r for r, m in requested] == ['summarizer', 'classifier', 'classifier']
    assert all(m == 'google/gemini-3.8-flash' for r, m in requested)
    assert len(json.loads(output.read_text())['traces']) == 3
