# cobol-wrap

Auto-generate production REST APIs from COBOL source files.

cobol-wrap parses COBOL programs, maps PIC clauses to Pydantic types, and emits
a complete FastAPI server — with OpenAPI spec, ctypes shim, Docker deployment,
and optional GraphQL, Kafka, and OpenTelemetry layers.

## Quick Start

```bash
# Install
pip install cobol-wrap

# Load a COBOL program into the local registry
cobol-wrap load ACCTMGMT.cbl

# Start the API server
cobol-wrap serve acctmgmt

# Browse the docs
open http://localhost:8080/docs
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `cobol-wrap load <file>` | Parse COBOL source and generate a REST API |
| `cobol-wrap serve <name>` | Start the FastAPI server for a loaded model |
| `cobol-wrap list` | List all loaded models with status and endpoints |
| `cobol-wrap inspect <name>` | Show detailed info about a model |
| `cobol-wrap rm <name>` | Remove a model from the registry |
| `cobol-wrap print api <name>` | Print the OpenAPI spec (YAML or `--json`) |
| `cobol-wrap ui` | Launch the interactive web dashboard |
| `cobol-wrap --version` | Show the installed version |

## How It Works

cobol-wrap uses a 4-stage pipeline:

```
COBOL Source (.cbl)
       |
  1. Preprocessor   — resolves COPY copybooks, intercepts EXEC SQL/CICS
       |
  2. Parser          — regex-based AST extraction (PIC, FD, LINKAGE, PROCEDURE)
       |
  3. Type Mapper     — maps COBOL PIC clauses to Pydantic models
       |
  4. Emitter         — generates FastAPI server, OpenAPI spec, ctypes shim
       |
  REST API (server.py, models.py, openapi.yaml, runtime/shim.py)
```

## Features

- **REST API Generation** — One POST route per PROCEDURE DIVISION entry point
- **Type-Safe Models** — PIC X(n) to `str`, PIC 9(n) to `int`, PIC 9(n)V99 to `Decimal`
- **Flat-File CRUD** — `--flat-files` generates GET/POST endpoints for FD records
- **VSAM Support** — `--vsam` backs indexed KSDS files with SQLite
- **Native Execution** — Compiles COBOL to shared libraries via GnuCOBOL, calls via ctypes
- **Docker Ready** — Auto-generated Dockerfile and docker-compose.yml
- **GraphQL** — `--graphql` generates a Strawberry GraphQL schema
- **Kafka Streaming** — `--kafka` generates FastStream consumer bindings
- **OpenTelemetry** — `--telemetry` injects distributed tracing
- **Copybook Resolution** — `--copybook-dir` resolves COPY includes
- **EXEC SQL/CICS** — Automatically intercepted and replaced with CALL stubs

## Load Options

```bash
cobol-wrap load PROGRAM.cbl \
  --name myapi \
  --flat-files \
  --vsam \
  --graphql \
  --kafka \
  --telemetry \
  --copybook-dir ./copybooks \
  --docker \
  --semantic
```

## Prerequisites

- **Python 3.9+**
- **GnuCOBOL** (optional, for native compilation):
  - macOS: `brew install gnucobol`
  - Ubuntu/Debian: `apt install gnucobol`

## Development

```bash
git clone https://github.com/your-org/cobol-wrap.git
cd cobol-wrap
pip install -e ".[dev,serve]"
pytest
```

## Architecture

```
cobol_wrap/
  __init__.py          # wrap() orchestrator
  ast.py               # Pydantic AST (CobolProgram, DataField, EntryPoint, FD)
  parser.py            # Regex-based COBOL parser
  preprocessor.py      # COPY/EXEC SQL/EXEC CICS preprocessor
  mapper.py            # PIC clause to Pydantic type mapper
  emitter.py           # FastAPI server + OpenAPI emitter
  bridge.py            # Flat-file CRUD bridge (SQLite VSAM adapter)
  runtime.py           # GnuCOBOL compile script + ctypes shim generator
  graphql_emitter.py   # Strawberry GraphQL emitter
  streaming.py         # FastStream Kafka emitter
  cli.py               # Typer CLI (Ollama-style UX)
  dashboard/           # Web UI dashboard
```

## License

Apache 2.0
