import os
import re
from typing import Any, Dict

import yaml

from .ast import CobolProgram, DataField


def _field_to_schema(field: DataField) -> Dict[str, Any]:
    """Convert a DataField to a JSON Schema object."""
    if field.children:
        props = {}
        for child in field.children:
            props[child.name.lower().replace('-', '_')] = _field_to_schema(child)
        return {"type": "object", "properties": props}

    pic = (field.pic_clause or "").upper().replace(" ", "")

    if getattr(field, 'is_pointer', False):
        return {"type": "integer", "description": "POINTER type"}

    if getattr(field, 'is_national', False):
        return {"type": "string", "description": "NATIONAL (Unicode) string"}

    # Fixed-point decimal: handles both V9(n) and V99 forms
    from .mapper import _parse_v_decimal
    dec_result = _parse_v_decimal(pic)
    if dec_result or field.is_comp3:
        if dec_result:
            int_digits, dec_places = dec_result
        else:
            int_digits, dec_places = 18, 4
        return {
            "type": "number",
            "format": "decimal",
            "description": f"Fixed-point: {int_digits + dec_places} digits, {dec_places} decimal places"
        }

    if 'S' in pic and '9' in pic:
        int_match = re.search(r'9\((\d+)\)', pic)
        digits = int(int_match.group(1)) if int_match else 4
        return {"type": "integer", "minimum": -(10 ** digits - 1), "maximum": 10 ** digits - 1}

    if '9' in pic or field.is_comp:
        int_match = re.search(r'9\((\d+)\)', pic)
        digits = int(int_match.group(1)) if int_match else 4
        return {"type": "integer", "minimum": 0, "maximum": 10 ** digits - 1}

    if 'X' in pic or 'A' in pic:
        str_match = re.search(r'[XA]\((\d+)\)', pic)
        if str_match:
            max_len = int(str_match.group(1))
        else:
            max_len = max(pic.count('X'), pic.count('A'))
        return {"type": "string", "maxLength": max_len}

    return {"type": "string"}


class OpenAPIEmitter:
    """ Generates openapi.yaml (OpenAPI 3.1) """
    def __init__(self, program: CobolProgram, title: str, version: str):
        self.program = program
        self.title = title
        self.version = version

    def to_dict(self) -> Dict[str, Any]:
        paths: Dict[str, Any] = {}
        schemas: Dict[str, Any] = {}

        # Build schemas from linkage section fields
        for field in self.program.linkage_section:
            schemas[field.name] = _field_to_schema(field)

        # Build schemas from FD record fields
        for fd in self.program.file_descriptions:
            for field in fd.fields:
                schemas[field.name] = _field_to_schema(field)

        # Build paths from procedure division entry points
        for ep in self.program.procedure_division:
            func_name = ep.name.lower().replace('-', '_')

            req_props: Dict[str, Any] = {}
            for param in ep.params:
                matched = next(
                    (f for f in self.program.linkage_section if f.name.upper() == param.upper()),
                    None
                )
                if matched:
                    req_props[param.lower().replace('-', '_')] = _field_to_schema(matched)

            paths[f"/{func_name}"] = {
                "post": {
                    "operationId": func_name,
                    "summary": f"Execute COBOL paragraph: {ep.name}",
                    "tags": ["COBOL Procedures"],
                    "requestBody": {
                        "required": bool(req_props),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": req_props
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Successful execution",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            }
                        },
                        "500": {"description": "COBOL runtime error"}
                    }
                }
            }

        # Build paths for flat-file FD CRUD endpoints
        for fd in self.program.file_descriptions:
            route = fd.name.lower()
            record_schema = {
                "type": "object",
                "properties": {
                    f.name.lower().replace('-', '_'): _field_to_schema(f)
                    for f in fd.fields
                }
            }
            paths[f"/{route}"] = {
                "get": {
                    "operationId": f"read_{route.replace('-', '_')}",
                    "summary": f"List all {fd.name} records",
                    "tags": ["Flat Files"],
                    "responses": {
                        "200": {
                            "description": "Record list",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "array", "items": record_schema}
                                }
                            }
                        }
                    }
                },
                "post": {
                    "operationId": f"create_{route.replace('-', '_')}",
                    "summary": f"Append a new {fd.name} record",
                    "tags": ["Flat Files"],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": record_schema}}
                    },
                    "responses": {
                        "200": {"description": "Success"}
                    }
                }
            }

        return {
            "openapi": "3.1.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": "Auto-generated REST API from COBOL source."
            },
            "paths": paths,
            "components": {
                "schemas": schemas
            }
        }

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), sort_keys=False)


class ServerEmitter:
    """ Generates FastAPI server.py """
    def __init__(self, program: CobolProgram, models: dict, openapi_spec: str, flat_files: bool = False):
        self.program = program
        self.models = models
        self.openapi_spec = openapi_spec
        self.flat_files = flat_files

    def emit(self, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "routes"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "runtime"), exist_ok=True)

        with open(os.path.join(output_dir, "openapi.yaml"), "w") as f:
            f.write(self.openapi_spec)

        from .mapper import TypeMapper
        mapper = TypeMapper(self.program, semantic=getattr(self, 'semantic', False))
        mapper.to_pydantic()

        with open(os.path.join(output_dir, "models.py"), "w") as f:
            f.write(mapper.generate_models_py())

        # Only import flatfiles if there are actual FD records to serve
        has_flat_files = self.flat_files and bool(self.program.file_descriptions)

        # Build server.py using a list to avoid blank lines from disabled features
        server_lines = [
            "# Auto-generated by cobol-wrap",
            "from fastapi import FastAPI",
            "from routes import procedure",
        ]
        if has_flat_files:
            server_lines.append("from routes import flatfiles")
        if getattr(self, 'graphql', False):
            server_lines.append("from routes import graphql_api")

        if getattr(self, 'telemetry', False):
            server_lines.extend([
                "",
                "from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor",
                "from opentelemetry import trace",
                "from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter",
                "from opentelemetry.sdk.trace import TracerProvider",
                "from opentelemetry.sdk.trace.export import BatchSpanProcessor",
                "",
                "provider = TracerProvider()",
                "processor = BatchSpanProcessor(OTLPSpanExporter())",
                "provider.add_span_processor(processor)",
                "trace.set_tracer_provider(provider)",
            ])

        server_lines.extend([
            "",
            f'app = FastAPI(title="{self.program.program_id} API")',
            "",
            "app.include_router(procedure.router)",
        ])
        if has_flat_files:
            server_lines.append("app.include_router(flatfiles.router)")
        if getattr(self, 'graphql', False):
            server_lines.append('app.include_router(graphql_api.graphql_app, prefix="/graphql")')

        if getattr(self, 'telemetry', False):
            server_lines.extend(["", "FastAPIInstrumentor.instrument_app(app)"])

        server_lines.extend([
            "",
            "",
            '@app.get("/health")',
            "def health():",
            '    return {"status": "ok"}',
            "",
        ])

        server_code = "\n".join(server_lines)
        with open(os.path.join(output_dir, "server.py"), "w") as f:
            f.write(server_code)

        procedure_code = f"""from fastapi import APIRouter
from models import *
{'from opentelemetry import trace' if getattr(self, 'telemetry', False) else ''}

router = APIRouter()
{'tracer = trace.get_tracer(__name__)' if getattr(self, 'telemetry', False) else ''}
"""
        procedure_code += f"""
import os
from fastapi import HTTPException
from runtime.shim import CobolRuntime
so_path = os.path.join(os.path.dirname(__file__), '..', 'runtime', '{self.program.program_id.lower()}.so')
try:
    runtime = CobolRuntime(so_path)
except Exception as e:
    print(f"Warning: COBOL Runtime failed to load binary. {{e}}")
    runtime = None
"""
        for ep in self.program.procedure_division:
            req_type = f"{ep.name.replace('-', '').capitalize()}Request"
            res_type = f"{ep.name.replace('-', '').capitalize()}Response"
            func_name = ep.name.lower().replace("-", "_")
            ep_span = f"with tracer.start_as_current_span('cobol_execute_{func_name}'):" if getattr(self, 'telemetry', False) else ""
            ind = "    " if ep_span else ""

            return_ok = "return result"

            procedure_code += f"""
@router.post('/{func_name}')
async def {func_name}(request: {req_type}):
    {ep_span}
    {ind}if not runtime:
    {ind}    raise HTTPException(status_code=503, detail='COBOL binary not loaded. Run compile.sh first.')
    {ind}result = runtime.call('{ep.name}', payload=request.model_dump())
    {ind}{return_ok}
"""
        with open(os.path.join(output_dir, "routes", "procedure.py"), "w") as f:
            f.write(procedure_code)

        with open(os.path.join(output_dir, "routes", "__init__.py"), "w") as f:
            f.write("")
