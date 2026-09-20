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
