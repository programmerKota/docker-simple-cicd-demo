# Contributing

1. Create a focused branch.
2. Add or update tests for every behavior change.
3. Run `ruff check .`, `mypy jarvis_home`, and `pytest`.
4. Do not weaken the policy engine to make a feature easier.
5. Never commit `.env`, `master.key`, Home Assistant tokens, recordings, or personal data.
6. Security-sensitive changes need a threat-model note in the pull request.

The project follows semantic versioning. Public tool schemas and persisted database behavior are treated as compatibility surfaces.
