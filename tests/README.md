# Test Suite

Create a local virtual environment and install the development extras:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Run the CI-ready pytest suite from the repository root:

```bash
.venv/bin/python -m pytest
```

The `scripts/test.sh` wrapper also runs this suite through
`.venv/bin/python -m pytest` and does not depend on a shell `PATH` pytest.

With coverage:

```bash
.venv/bin/python -m pytest --cov=variant_pathogenicity_rater --cov=mcp-server --cov-report=term-missing
```

The suite uses shared fixtures in `tests/conftest.py` plus deterministic mock data in `tests/fixtures/` and `examples/`. Tests stay inside the documented module boundaries: evidence providers create evidence records, ACMG evaluators apply criteria, the combiner classifies already-triggered evidence, reporting renders structured results, and MCP tests only verify tool registration and orchestration smoke paths.

Coverage settings live in `pyproject.toml` under `[tool.coverage.*]`. The
coverage command requires `pytest-cov`, which is isolated in the `coverage`
optional dependency group.
