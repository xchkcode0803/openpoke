"""Eval candidates and independent judge identities."""

SONNET = "anthropic/claude-sonnet-4"
GEMINI = "google/gemini-3.8-flash"
JEV = "typesafe/jev-1.13"
MODELS = {"sonnet": SONNET, "gemini": GEMINI}
JUDGES = (JEV, SONNET)
