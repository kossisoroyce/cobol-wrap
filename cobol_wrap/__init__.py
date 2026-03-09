"""
cobol-wrap: Auto-generate production REST APIs from COBOL source files.

Parses COBOL programs, maps PIC clauses to Pydantic types, and emits a
complete FastAPI server with OpenAPI spec, ctypes shim, Docker config,
and optional GraphQL / Kafka / telemetry layers.
"""

__version__ = "1.0.0"

import os
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("cobol_wrap")

COBOL_EXTENSIONS = {".cbl", ".cob", ".cpy", ".CBL", ".COB", ".CPY"}


def wrap(
    program_path: str,
    output_dir: str = "./cobol-api",
    filename: str = None,
    framework: str = "fastapi",
    docker: bool = True,
    flat_files: bool = False,
    vsam: bool = False,
    graphql: bool = False,
    kafka: bool = False,
    telemetry: bool = False,
    semantic: bool = False,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Main orchestration function — parses COBOL source and generates a
    production REST API.

    Returns a summary dict with counts and metadata for the CLI to display.
    """
    from .parser import CobolParser
    from .mapper import TypeMapper
    from .emitter import OpenAPIEmitter, ServerEmitter
    from .bridge import FlatFileBridgeEmitter

    def _progress(msg: str):
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    # --- Pre-validation ---
    if not os.path.exists(program_path):
        raise FileNotFoundError(
            f"COBOL source file not found: {program_path}\n\n"
            f"  Make sure you're passing the full path to your COBOL source file.\n"
            f"  Example: cobol-wrap load ./programs/ACCTMGMT.cbl"
        )

    if os.path.getsize(program_path) == 0:
        raise ValueError(
            f"COBOL source file is empty: {program_path}\n\n"
            f"  The file exists but contains no data."
        )

    # --- 1. Parse ---
    _progress("Parsing COBOL source...")
    parser = CobolParser()
    program = parser.parse(program_path)
    logger.info("Parsed program: %s (%d entry points, %d linkage fields, %d FDs)",
                program.program_id, len(program.procedure_division),
                len(program.linkage_section), len(program.file_descriptions))

    # --- 2. Map types ---
    _progress("Mapping COBOL types to Pydantic models...")
    mapper = TypeMapper(program, semantic=semantic)
    models = mapper.to_pydantic()

    # --- 3. Emit OpenAPI ---
    _progress("Generating OpenAPI 3.1 specification...")
    openapi_emitter = OpenAPIEmitter(
        program, title=filename or os.path.basename(program_path), version=__version__
    )
    openapi_spec = openapi_emitter.to_yaml()

    # --- 4. Generate server, routes, models ---
    _progress("Generating FastAPI server and routes...")
    server_emitter = ServerEmitter(
        program, models, openapi_spec, flat_files=flat_files or vsam
    )
    server_emitter.telemetry = telemetry
    server_emitter.graphql = graphql
    server_emitter.semantic = semantic
    server_emitter.emit(output_dir)

    # --- 5. Runtime packaging (compile script + ctypes shim) ---
    _progress("Packaging GnuCOBOL runtime and ctypes shim...")
    from .runtime import RuntimePackager
    RuntimePackager.emit(output_dir, program, docker=docker, source_path=program_path,
                         graphql=graphql, kafka=kafka, telemetry=telemetry)

    # --- 6. Optional layers ---
    if flat_files or vsam:
        _progress("Generating flat-file CRUD bridge...")
        bridge_emitter = FlatFileBridgeEmitter(program)
        bridge_emitter.emit(output_dir)

    if graphql:
        _progress("Generating Strawberry GraphQL schema...")
        from .graphql_emitter import GraphQLEmitter
        gql = GraphQLEmitter(program, models)
        gql.emit(output_dir)

    if kafka:
        _progress("Generating FastStream Kafka consumers...")
        from .streaming import StreamingEmitter
        stream = StreamingEmitter(program)
        stream.emit(output_dir)

    # --- Summary ---
    features = []
    if flat_files:
        features.append("flat-files")
    if vsam:
        features.append("vsam")
    if graphql:
        features.append("graphql")
    if kafka:
        features.append("kafka")
    if telemetry:
        features.append("telemetry")
    if docker:
        features.append("docker")

    return {
        "program_id": program.program_id,
        "endpoints": len(program.procedure_division),
        "models": len(models),
        "file_descriptions": len(program.file_descriptions),
        "working_storage_groups": len(program.working_storage),
        "linkage_fields": len(program.linkage_section),
        "features": features,
        "output_dir": output_dir,
    }
