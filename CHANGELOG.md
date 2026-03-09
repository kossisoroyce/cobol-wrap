# Changelog

All notable changes to cobol-wrap are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

---

## [1.0.1] — 2026-03-09

### Fixed

- CI: Added `httpx` to dev dependencies (required by FastAPI TestClient)
- CI: Skip native runtime tests when `libcob` is not available on macOS runners
- CI: Fixed compiled library discovery filtering out `bridges.so` stub
- Lint: Fixed all ruff warnings (import sorting, trailing whitespace, ambiguous variable names)

## [1.0.0] — 2026-03-09

### Added

- **Ollama-style CLI** — `cobol-wrap load`, `serve`, `list`, `inspect`, `rm`, `print api`, `ui` with rich terminal output, warm/helpful error messages, and progress feedback
- **4-stage COBOL pipeline** — Preprocessor (COPY/EXEC SQL/CICS) → Regex Parser → PIC-to-Pydantic Mapper → FastAPI Emitter
- **REST API generation** — one POST route per PROCEDURE DIVISION entry point with Pydantic request/response models
- **OpenAPI 3.1 spec** — auto-generated from COBOL PIC clauses with JSON Schema types
- **Flat-file CRUD** — `--flat-files` generates GET/POST endpoints for FD records (sequential append)
- **VSAM support** — `--vsam` backs indexed KSDS files with SQLite, full CRUD (GET/POST/PUT/DELETE)
- **Native execution** — GnuCOBOL compilation to shared libraries via `cobc`, ctypes shim with automatic struct mapping
- **GraphQL layer** — `--graphql` generates Strawberry GraphQL schema with `strawberry.scalars.JSON` typed mutations
- **Kafka streaming** — `--kafka` generates FastStream consumer bindings with per-entry-point topics
- **OpenTelemetry** — `--telemetry` injects distributed tracing spans per COBOL call
- **Docker deployment** — auto-generated Dockerfile and docker-compose.yml with conditional Kafka/OTLP services
- **Copybook resolution** — `--copybook-dir` resolves COPY includes at preprocessing stage
- **EXEC SQL/CICS interception** — automatically replaced with CALL stubs and bridge functions
- **Web dashboard** — `cobol-wrap ui` launches an interactive model browser
- **Semantic mode** — `--semantic` generates human-friendly field names in Pydantic models
- **Production ctypes shim** — COMP-3 BCD byte sizing, COMP integer sizing (c_int16/32/64), OCCURS array expansion, POINTER support, NATIONAL string support
- **Comprehensive test suite** — 139 tests covering parser, mapper, emitter, bridge, runtime, CLI, and end-to-end pipelines

### Security

- SQL injection prevention via `_sanitize_identifier()` in VSAM bridge
- COBOL source validation rejects non-COBOL files with helpful error messages
- Generated API returns proper HTTP error codes (400, 404, 413, 500, 503)

[Unreleased]: https://github.com/kossisoroyce/cobol-wrap/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/kossisoroyce/cobol-wrap/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/kossisoroyce/cobol-wrap/releases/tag/v1.0.0
