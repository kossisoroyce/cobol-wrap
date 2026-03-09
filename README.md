# cobol-wrap

<p align="center">
  <strong>Turn COBOL programs into production REST APIs. One command to load, one command to serve.</strong>
</p>

<p align="center">
  <a href="https://github.com/kossisoroyce/cobol-wrap/actions/workflows/ci.yml"><img src="https://github.com/kossisoroyce/cobol-wrap/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/cobol-wrap/"><img src="https://img.shields.io/pypi/v/cobol-wrap.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/cobol-wrap/"><img src="https://img.shields.io/pypi/pyversions/cobol-wrap.svg" alt="Python versions"></a>
  <a href="https://pypi.org/project/cobol-wrap/"><img src="https://img.shields.io/pypi/dm/cobol-wrap.svg" alt="Monthly downloads"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache-2.0"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#cli-reference">CLI Reference</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="https://pypi.org/project/cobol-wrap/">PyPI</a>
</p>

---

cobol-wrap parses COBOL source files, maps PIC clauses to Pydantic types, and generates a **complete FastAPI server** — with OpenAPI spec, ctypes shim, typed models, and optional GraphQL, Kafka, OpenTelemetry, and Docker layers. The generated API calls the original COBOL program natively via GnuCOBOL shared libraries.

> **Parse → Map → Emit → Serve. From COBOL to REST in seconds.**

---

## See it in action

```console
$ pip install cobol-wrap

$ cobol-wrap load ACCTMGMT.cbl

  Parsing COBOL source...
  Mapping COBOL types to Pydantic models...
  Generating OpenAPI 3.1 specification...
  Generating FastAPI server and routes...
  Packaging GnuCOBOL runtime and ctypes shim...

  ╭─ Model Loaded Successfully ─────────────────────────╮
  │                                                      │
  │  Name         acctmgmt                               │
  │  Endpoints    1                                      │
  │  Models       3                                      │
  │  Features     docker                                 │
  │  Output       ./cobol-api                            │
  │                                                      │
  ╰──────────────────────────────────────────────────────╯

$ cobol-wrap serve acctmgmt

  Serving  acctmgmt  on  http://localhost:8080
  Docs     http://localhost:8080/docs

  POST  /acctmgmt     Execute COBOL paragraph
  GET   /health       Health check
```

**Call the API immediately:**

```console
$ curl -s http://localhost:8080/acctmgmt \
    -H 'Content-Type: application/json' \
    -d '{"lk_acct_id": "12345", "lk_action": "INQUIRY"}'

{"lk_acct_id": "12345", "lk_balance": "000050000", "lk_status": "00"}
```

---

## Table of Contents

- [Who is this for?](#who-is-this-for)
- [How it works](#how-it-works)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Load Options](#load-options)
- [Features](#features)
- [Generated Output](#generated-output)
- [Type Mapping](#type-mapping)
- [COBOL Constructs Supported](#cobol-constructs-supported)
- [Examples](#examples)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [Prerequisites](#prerequisites)
- [Development](#development)
- [Community & Governance](#community--governance)
- [License](#license)

---

## Who is this for?

cobol-wrap is built for teams modernizing COBOL systems without rewriting them:

- **Banks & financial institutions** — expose mainframe business logic as REST APIs for mobile banking, fintech integrations, and microservice architectures
- **Insurance & healthcare** — wrap batch COBOL programs (claims processing, eligibility checks) as on-demand services
- **Government agencies** — modernize legacy COBOL systems with zero business logic rewrite
- **Platform & migration teams** — create API facades over COBOL while planning long-term rewrites
- **DevOps teams** — containerize COBOL workloads with auto-generated Dockerfiles and CI/CD-ready artifacts

---

## How it works

```
  ┌──────────────────────────────────────────────────────────────┐
  │                     cobol-wrap load                          │
  │                                                              │
  │  COBOL source  ──►  Preprocessor  ──►  Parser  ──►  Mapper  │
  │  (.cbl/.cob)        (COPY, EXEC       (regex AST)   (PIC →  │
  │                      SQL/CICS)                       Pydantic)│
  │                                           │                  │
  │                                           ▼                  │
  │                                        Emitter               │
  │                                           │                  │
  │                  ┌────────────────────────┼──────────────┐   │
  │                  ▼            ▼           ▼              ▼   │
  │             server.py    models.py   openapi.yaml    shim.py │
  │             (FastAPI)    (Pydantic)  (OpenAPI 3.1)   (ctypes)│
  │                  │                                           │
  │                  └──► cobc ──► program.so ──► native calls   │
  └──────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    cobol-wrap serve <name>
                 http://localhost:8080/docs
```

The pipeline:

1. **Preprocess** — resolves `COPY` copybook includes, intercepts `EXEC SQL` and `EXEC CICS` blocks and replaces them with bridge `CALL` stubs
2. **Parse** — regex-based extraction of PROGRAM-ID, WORKING-STORAGE, LINKAGE SECTION, FILE SECTION (FD), and PROCEDURE DIVISION into a typed AST
3. **Map** — converts COBOL PIC clauses to Pydantic v2 models with proper constraints (`maxLength`, `max_digits`, `ge`/`le`, enums from 88-level values)
4. **Emit** — generates a FastAPI server, OpenAPI 3.1 spec, Pydantic models, and ctypes shim that calls the compiled COBOL shared library
5. **Package** — produces a `compile.sh` script, Dockerfile, docker-compose.yml, and requirements.txt

---

## Quick Start

```bash
pip install cobol-wrap
```

**Load and serve a COBOL program:**

```bash
cobol-wrap load PAYROLL.cbl
cobol-wrap serve payroll
```

**Browse the auto-generated API docs:**

```bash
open http://localhost:8080/docs
```

**With all the bells and whistles:**

```bash
cobol-wrap load CUSTMGMT.cbl \
  --flat-files \
  --vsam \
  --graphql \
  --kafka \
  --telemetry \
  --docker \
  --copybook-dir ./copybooks
```

---

## CLI Reference

cobol-wrap uses an Ollama-style CLI — simple, memorable commands with rich terminal output.

```
cobol-wrap load <file>           Parse COBOL source and generate a REST API
cobol-wrap serve <name>          Start the FastAPI server for a loaded model
cobol-wrap list                  List all loaded models with status and endpoints
cobol-wrap inspect <name>        Show detailed info about a model (fields, routes, features)
cobol-wrap rm <name>             Remove a model from the registry
cobol-wrap print api <name>      Print the OpenAPI spec (YAML or --json)
cobol-wrap ui                    Launch the interactive web dashboard
cobol-wrap --version             Show the installed version
```

### Examples

```bash
# Load with a custom name
cobol-wrap load ACCTMGMT.cbl --name account-api

# List everything
cobol-wrap list

# Inspect a model's routes and fields
cobol-wrap inspect account-api

# Print the OpenAPI spec as JSON
cobol-wrap print api account-api --json

# Serve on a custom port
cobol-wrap serve account-api --port 9090

# Clean up
cobol-wrap rm account-api
```

---

## Load Options

| Flag | Description |
|------|-------------|
| `--name TEXT` | Custom name for the loaded model (default: PROGRAM-ID) |
| `--flat-files` | Generate GET/POST CRUD endpoints for FD file records |
| `--vsam` | Back indexed FD files with SQLite (full CRUD: GET/POST/PUT/DELETE) |
| `--graphql` | Generate a Strawberry GraphQL schema alongside REST |
| `--kafka` | Generate FastStream Kafka consumer bindings per entry point |
| `--telemetry` | Inject OpenTelemetry distributed tracing spans |
| `--docker` | Generate Dockerfile and docker-compose.yml |
| `--copybook-dir PATH` | Directory containing COPY copybook includes |
| `--semantic` | Generate human-friendly field names in Pydantic models |
| `--verbose` | Enable detailed logging output |

---

## Features

### REST API Generation

One POST route per PROCEDURE DIVISION entry point. Request and response models are auto-generated from the LINKAGE SECTION with full Pydantic validation.

### Type-Safe Pydantic Models

| COBOL PIC | Python type | Constraints |
|-----------|-------------|-------------|
| `PIC X(20)` | `str` | `max_length=20` |
| `PIC A(10)` | `str` | `max_length=10` |
| `PIC 9(8)` | `int` | `ge=0, le=99999999` |
| `PIC S9(4)` | `int` | `ge=-9999, le=9999` |
| `PIC 9(8)V99` | `Decimal` | `max_digits=10, decimal_places=2` |
| `PIC 9(4)V99 COMP-3` | `Decimal` | Packed BCD, mapped to decimal |
| `PIC S9(4) COMP` | `int` | Binary integer, proper sizing |
| `88 STATUS-ACTIVE VALUE 'A'` | `Enum` | Auto-generated from 88-level values |
| `OCCURS 10 TIMES` | `List[...]` | `min_length=10, max_length=10` |
| `USAGE POINTER` | `int` | Pointer type |
| `PIC N(20)` | `str` | NATIONAL (Unicode) string |

### Flat-File CRUD

`--flat-files` generates GET and POST endpoints for each FD record definition. Sequential files use append-mode flat files. Indexed files use SQLite with the RECORD KEY as primary key.

### VSAM Support

`--vsam` extends flat-file support with full CRUD operations for indexed (KSDS) files:

- **POST** `/route` — create a new record (enforces unique key)
- **GET** `/route` — list all records, or `?id=KEY` for lookup
- **PUT** `/route/{id}` — update (REWRITE) an existing record
- **DELETE** `/route/{id}` — delete a record

Backed by SQLite — no VSAM installation required.

### Native COBOL Execution

The generated ctypes shim maps COBOL Working-Storage and Linkage Section fields to C structures, then calls the compiled GnuCOBOL shared library directly. No subprocess overhead — pure in-process native calls.

Supported COBOL storage types in the shim:

| COBOL | ctypes mapping |
|-------|---------------|
| `PIC X(n)` / `PIC A(n)` | `c_char * n` |
| `PIC 9(n)` (display) | `c_char * n` |
| `PIC 9(n) COMP-3` | `c_char * ((n+2)//2)` (packed BCD) |
| `PIC S9(1-4) COMP` | `c_int16` / `c_uint16` |
| `PIC S9(5-9) COMP` | `c_int32` / `c_uint32` |
| `PIC S9(10-18) COMP` | `c_int64` / `c_uint64` |
| `USAGE POINTER` | `c_void_p` |
| `OCCURS N TIMES` | `Type * N` (ctypes array) |

### GraphQL

`--graphql` generates a Strawberry GraphQL schema with:
- One GQL type per Pydantic model
- Mutations per PROCEDURE DIVISION entry point
- Health query
- Mounted at `/graphql` with GraphiQL explorer

### Kafka Streaming

`--kafka` generates FastStream consumer bindings:
- Input topic: `cobol.<program>.<entry_point>.in`
- Output topic: `cobol.<program>.<entry_point>.out`
- One async consumer per entry point

### OpenTelemetry

`--telemetry` injects distributed tracing:
- `TracerProvider` with OTLP HTTP exporter
- Per-route spans (`cobol_execute_<entry_point>`)
- `FastAPIInstrumentor` for automatic HTTP span capture

### Docker Deployment

`--docker` generates:
- `Dockerfile` — Python 3.11-slim + GnuCOBOL, auto-compiles COBOL source
- `docker-compose.yml` — API service, plus Kafka (Zookeeper + broker) and OTLP collector when those features are enabled
- `requirements.txt` — always generated, includes conditional deps for enabled features

### Copybook Resolution

`--copybook-dir` resolves `COPY` includes at the preprocessing stage. Nested copybooks are supported.

### EXEC SQL / EXEC CICS

`EXEC SQL ... END-EXEC` and `EXEC CICS ... END-EXEC` blocks are automatically intercepted and replaced with `CALL 'SQL-BRIDGE'` / `CALL 'CICS-BRIDGE'` stubs. The generated `compile.sh` includes bridge C functions so GnuCOBOL links cleanly.

---

## Generated Output

After `cobol-wrap load`, the output directory contains:

```
cobol-api/
├── server.py              # FastAPI application (entry point)
├── models.py              # Pydantic v2 models from COBOL PIC clauses
├── openapi.yaml           # OpenAPI 3.1 specification
├── requirements.txt       # Python dependencies (always generated)
├── routes/
│   ├── __init__.py
│   ├── procedure.py       # POST routes for PROCEDURE DIVISION entry points
│   ├── flatfiles.py       # CRUD routes for FD records (if --flat-files/--vsam)
│   ├── graphql_api.py     # Strawberry GraphQL schema (if --graphql)
│   └── kafka_consumers.py # FastStream Kafka consumers (if --kafka)
├── runtime/
│   ├── shim.py            # ctypes C-struct mapping + CobolRuntime class
│   ├── compile.sh         # GnuCOBOL compilation script
│   └── <program>.cbl      # Copy of the COBOL source
├── Dockerfile             # (if --docker)
└── docker-compose.yml     # (if --docker)
```

---

## COBOL Constructs Supported

| Construct | Support |
|-----------|---------|
| `IDENTIFICATION DIVISION` | PROGRAM-ID extraction |
| `DATA DIVISION` | WORKING-STORAGE, LINKAGE SECTION, FILE SECTION |
| `PROCEDURE DIVISION USING` | Entry point + parameter extraction |
| `PIC X/A/9/S9/V` | Full type mapping with constraints |
| `COMP` / `BINARY` | Binary integer (sized by digit count) |
| `COMP-3` / `PACKED-DECIMAL` | Packed BCD (sized by byte count) |
| `USAGE POINTER` | Void pointer |
| `PIC N` / `NATIONAL` | Unicode string |
| `OCCURS N TIMES` | Fixed-length arrays |
| `OCCURS n TO m TIMES DEPENDING ON` | Variable-length arrays (max size used) |
| `REDEFINES` | Tracked in AST (redefines field recorded) |
| `88-level VALUES` | Enum generation |
| `FD` records | File descriptions with field hierarchies |
| `ORGANIZATION IS INDEXED` | VSAM KSDS detection |
| `RECORD KEY IS` | Primary key extraction for VSAM |
| `COPY` | Copybook include resolution |
| `EXEC SQL / EXEC CICS` | Intercepted and replaced with bridge stubs |
| Nested group hierarchies | Recursive field nesting (01 → 05 → 10 → ...) |

---

## Examples

The [`examples/`](examples/) directory contains sample COBOL programs. The [`tests/cobol/`](tests/cobol/) directory contains programs exercising every supported construct:

| File | What it tests |
|------|---------------|
| `ACCTMGMT.cbl` | Account management with linkage parameters |
| `payroll.cbl` | Decimal arithmetic, COMP-3, OCCURS, 88-level enums |
| `inventory.cbl` | FD records, flat-file CRUD |
| `customer_vsam.cbl` | VSAM indexed KSDS with RECORD KEY |
| `data_types.cbl` | Every PIC clause variant |
| `compute.cbl` | Arithmetic operations |
| `sql_bridge.cbl` | EXEC SQL interception |
| `cics_bridge.cbl` | EXEC CICS interception |
| `with_copy.cbl` | COPY copybook resolution |

---

## Limitations

- **GnuCOBOL required for native execution** — without it, the API server starts but returns 503 for COBOL calls until the shared library is compiled
- **Regex-based parser** — handles standard COBOL constructs well but may miss exotic vendor extensions or deeply non-standard formatting
- **COMP-3 interop** — packed BCD values are mapped correctly at the byte level, but complex COMP-3 arithmetic in Working-Storage may need manual validation
- **No CICS/DB2 runtime** — `EXEC SQL` and `EXEC CICS` are replaced with stubs; actual database/transaction calls require a real middleware layer
- **Single entry point per PROCEDURE DIVISION** — the parser extracts `PROCEDURE DIVISION USING` parameters; multiple `ENTRY` statements are not yet supported
- **Copybook nesting** — `COPY ... REPLACING` is not yet supported; basic `COPY` includes work

---

## Roadmap

| Status | Item |
|--------|------|
| Done | Regex-based COBOL parser with full PIC/FD/LINKAGE/PROCEDURE support |
| Done | Pydantic v2 type mapper with constraints, enums, decimals |
| Done | FastAPI server + OpenAPI 3.1 emitter |
| Done | ctypes shim with COMP/COMP-3/POINTER/OCCURS/NATIONAL support |
| Done | Flat-file CRUD + VSAM SQLite adapter (full CRUD) |
| Done | GraphQL, Kafka, OpenTelemetry optional layers |
| Done | Docker deployment with conditional services |
| Done | Ollama-style CLI with rich terminal output |
| Done | PyPI packaging with OIDC trusted publishing |
| Planned | Multiple `ENTRY` statement support |
| Planned | `COPY ... REPLACING` preprocessing |
| Planned | DB2 SQL bridge with actual database connectivity |
| Planned | CICS transaction bridge |
| Planned | gRPC endpoint generation alongside REST |
| Planned | Batch file processing mode (read/transform/write FD records) |

---

## Prerequisites

- **Python 3.9+**
- **GnuCOBOL** (optional, for native COBOL execution):
  - macOS: `brew install gnucobol`
  - Ubuntu/Debian: `sudo apt install gnucobol`
  - RHEL/CentOS: `sudo yum install gnucobol`

Without GnuCOBOL, cobol-wrap still generates all API code, models, and specs — the compiled shared library just won't be available until you install it and run `compile.sh`.

---

## Development

```bash
git clone https://github.com/kossisoroyce/cobol-wrap.git
cd cobol-wrap
pip install -e ".[dev,serve]"
pytest tests/ -v                    # 139 tests
ruff check cobol_wrap/              # linting
```

The test suite covers: parser (PIC clauses, FD records, VSAM, OCCURS, REDEFINES, copybooks, EXEC SQL/CICS), mapper (type mapping, enums, decimals, groups), emitter (server.py, models.py, OpenAPI spec, procedure routes), bridge (flat-file CRUD, VSAM SQLite), runtime (ctypes shim, compile script, struct mapping), CLI (load, serve, list, inspect), and full end-to-end pipelines.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full development guide.

---

## Community & Governance

- **Contributing:** [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Code of conduct:** [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- **Security policy:** [`SECURITY.md`](SECURITY.md)
- **Changelog:** [`CHANGELOG.md`](CHANGELOG.md)

Bugs and feature requests: [open an issue](https://github.com/kossisoroyce/cobol-wrap/issues).

---

## Support the Project

cobol-wrap is developed and maintained by [Electric Sheep Africa](https://github.com/electricsheepafrica). If it saves your team engineering time, consider supporting continued development:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-%23FFDD00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/electricsheepafrica)

---

## License

Apache-2.0 — see [`LICENSE`](LICENSE) for the full text.
