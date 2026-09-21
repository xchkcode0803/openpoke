"""All application roles switch together; independent eval judges stay fixed."""


def test_five_application_defaults_and_fixed_judges():
    from server.config import Settings
    from evals.agent_overload.metrics import JEV_MODEL, FALLBACK_MODEL
    settings = Settings()
    roles = ('interaction_agent_model', 'execution_agent_model',
             'execution_agent_search_model', 'summarizer_model', 'email_classifier_model')
    assert {getattr(settings, role) for role in roles} == {'google/gemini-3.8-flash'}
    assert JEV_MODEL == 'typesafe/jev-1.13'
    assert FALLBACK_MODEL == 'anthropic/claude-sonnet-4'
    assert settings.conversation_summary_threshold == 100
    assert settings.conversation_summary_tail_size == 10


def test_source_fingerprints_cover_eval_implementation_not_tests():
    from evals.shared.provenance import eval_source_hashes

    hashes = eval_source_hashes()
    assert "evals/agent_gmail/cases.py" in hashes
    assert "evals/model_comparison/render.py" in hashes
    assert "evals/shared/models.py" in hashes
    assert not any(path.startswith("evals/live/") or "/test_" in path for path in hashes)
