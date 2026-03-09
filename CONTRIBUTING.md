# Contributing to cobol-wrap

Thanks for your interest in contributing to cobol-wrap! This guide will help you get set up.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/kossisoroyce/cobol-wrap.git
cd cobol-wrap

# Install in development mode with all dependencies
pip install -e ".[dev,serve]"

# Verify everything works
pytest tests/ -v
```

**Requirements:**

- Python 3.9+
- GnuCOBOL (optional, for native compilation tests):
  - macOS: `brew install gnucobol`
  - Ubuntu/Debian: `apt install gnucobol`
- `pytest` for testing (installed with `[dev]` extras)

## Running Tests

```bash
# Full suite (139 tests)
pytest tests/ -v

# Specific test file
pytest tests/test_parser.py -v

# Specific test
pytest tests/test_parser.py::TestParser::test_linkage_section -v

# With coverage
pytest tests/ --cov=cobol_wrap --cov-report=html
```

## Project Structure

```
cobol_wrap/
├── __init__.py          # wrap() orchestrator
├── ast.py               # Pydantic AST (CobolProgram, DataField, EntryPoint, FD)
├── parser.py            # Regex-based COBOL parser
├── preprocessor.py      # COPY/EXEC SQL/EXEC CICS preprocessor
├── mapper.py            # PIC clause to Pydantic type mapper
├── emitter.py           # FastAPI server + OpenAPI emitter
├── bridge.py            # Flat-file CRUD bridge (SQLite VSAM adapter)
├── runtime.py           # GnuCOBOL compile script + ctypes shim generator
├── graphql_emitter.py   # Strawberry GraphQL emitter
├── streaming.py         # FastStream Kafka emitter
├── cli.py               # Typer CLI (Ollama-style UX)
└── dashboard/           # Web UI dashboard
```

## How It Works

cobol-wrap uses a 4-stage pipeline:

1. **Preprocessor** — resolves COPY copybooks, intercepts EXEC SQL/CICS
2. **Parser** — regex-based AST extraction (PIC, FD, LINKAGE, PROCEDURE)
3. **Type Mapper** — maps COBOL PIC clauses to Pydantic models
4. **Emitter** — generates FastAPI server, OpenAPI spec, ctypes shim

## Code Style

- Use `ruff` for linting (configured in `pyproject.toml`)
- Type hints on all new function signatures
- Docstrings on public classes/functions
- Keep generated code clean — no dead imports or unused variables

## Pull Request Process

1. Fork the repo and create your branch from `main`
2. Write tests for any new functionality
3. Ensure all tests pass: `pytest tests/ -v`
4. Update CHANGELOG.md under `[Unreleased]`
5. Submit a PR using the pull request template
