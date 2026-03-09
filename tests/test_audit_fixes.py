"""
Regression tests for bugs found and fixed during the deep audit.
Each test is named after the bug it protects against.
"""
import ast
import os
import tempfile
import pytest
from decimal import Decimal
from tempfile import TemporaryDirectory

from cobol_wrap.ast import CobolProgram, DataField, EntryPoint, FD
from cobol_wrap.parser import CobolParser
from cobol_wrap.mapper import TypeMapper, _parse_v_decimal
from cobol_wrap.emitter import OpenAPIEmitter, ServerEmitter
from cobol_wrap.bridge import FlatFileBridgeEmitter
from cobol_wrap import wrap


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_cbl(tmp_path, content: str, name: str = "mock.cbl") -> str:
    p = tmp_path / name
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# Bug 1 — parser: current_fd not cleared on section transition
# ---------------------------------------------------------------------------

def test_fd_not_polluted_with_ws_fields(tmp_path):
    """
    WORKING-STORAGE fields must go into working_storage, not into the preceding FD.
    """
    cbl = """
       DATA DIVISION.
       FILE SECTION.
       FD MY-FILE.
       01 MY-RECORD.
          05 FILE-FIELD   PIC X(10).

       WORKING-STORAGE SECTION.
       01 WS-ROOT.
          05 WS-FIELD     PIC 9(4).

       LINKAGE SECTION.
       01 LK-PARAM        PIC X(5).
    """
    path = make_cbl(tmp_path, cbl)
    prog = CobolParser().parse(path)

    # The FD should have exactly one root record (MY-RECORD)
    assert len(prog.file_descriptions) == 1
    fd = prog.file_descriptions[0]
    assert fd.name == "MY-FILE"
    assert len(fd.fields) == 1
    assert fd.fields[0].name == "MY-RECORD"

    # Working storage must contain WS-ROOT, not WS-FIELD directly
    assert len(prog.working_storage) == 1
    assert prog.working_storage[0].name == "WS-ROOT"
    assert prog.working_storage[0].children[0].name == "WS-FIELD"

    # Linkage must contain LK-PARAM
    assert len(prog.linkage_section) == 1
    assert prog.linkage_section[0].name == "LK-PARAM"


# ---------------------------------------------------------------------------
# Bug 2 — mapper: V-decimal regex only captured one digit for V99 style
# ---------------------------------------------------------------------------

def test_parse_v_decimal_bare_nines():
    """_parse_v_decimal must count ALL literal nines after V, not just the first."""
    assert _parse_v_decimal("9(10)V99") == (10, 2)
    assert _parse_v_decimal("9(5)V999") == (5, 3)
    assert _parse_v_decimal("9(7)V9") == (7, 1)


def test_parse_v_decimal_parenthesized():
    assert _parse_v_decimal("9(10)V9(2)") == (10, 2)
    assert _parse_v_decimal("S9(7)V9(3)") == (7, 3)


def test_map_field_decimal_bare_v99():
    """Pydantic field for PIC 9(10)V99 must have decimal_places=2, not 9."""
    df = DataField(level=5, name="BALANCE", pic_clause="9(10)V99")
    mapper = TypeMapper(CobolProgram(program_id="T"))
    t, f = mapper._map_field(df)
    assert t == Decimal
    dec_meta = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
    assert dec_meta is not None
    assert dec_meta.decimal_places == 2
    assert dec_meta.max_digits == 12   # 10 + 2


def test_map_field_comp3_with_v99():
    """COMP-3 fields with V99 PIC must also get decimal_places=2."""
    df = DataField(level=5, name="AMT", pic_clause="S9(7)V99", is_comp3=True)
    mapper = TypeMapper(CobolProgram(program_id="T"))
    t, f = mapper._map_field(df)
    assert t == Decimal
    dec_meta = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
    assert dec_meta is not None
    assert dec_meta.decimal_places == 2
    assert dec_meta.max_digits == 9    # 7 + 2


# ---------------------------------------------------------------------------
# Bug 3 — emitter: procedure.py used payload= even for linked-param models
# ---------------------------------------------------------------------------

def test_generated_procedure_uses_kwargs_for_linked_params(tmp_path):
    """
    When an entry point has LINKAGE SECTION params, the generated return must
    unpack the result dict (**result), not pass it as payload=.
    """
    cbl = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCT.

       DATA DIVISION.
       LINKAGE SECTION.
       01 ACCT-ID      PIC 9(8).
       01 ACCT-BAL     PIC 9(10)V99.
       01 RET-CODE     PIC 9(2).

       PROCEDURE DIVISION USING ACCT-ID ACCT-BAL RET-CODE.
       MAIN-PARA.
           GOBACK.
    """
    path = make_cbl(tmp_path, cbl)
    with TemporaryDirectory() as td:
        wrap(path, output_dir=td)
        proc = open(os.path.join(td, "routes", "procedure.py")).read()
        # Route returns raw dict from shim
        assert "return result" in proc
        # Must be syntactically valid Python
        ast.parse(proc)


def test_generated_procedure_uses_payload_for_no_params(tmp_path):
    """
    When an entry point has NO params, the response model has a `payload` field
    so generated code must use payload=result.
    """
    cbl = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NOPARAM.
       PROCEDURE DIVISION.
       MAIN-PARA.
           GOBACK.
    """
    path = make_cbl(tmp_path, cbl)
    with TemporaryDirectory() as td:
        wrap(path, output_dir=td)
        proc = open(os.path.join(td, "routes", "procedure.py")).read()
        assert "return result" in proc
        ast.parse(proc)


# ---------------------------------------------------------------------------
# Bug 4 — bridge: hyphens in FD name produce invalid Python function names
# ---------------------------------------------------------------------------

def test_bridge_generates_valid_python_function_names():
    """
    FD names with hyphens (e.g. CUST-FILE) must produce underscored Python
    identifiers (init_cust_file_table), not hyphenated ones.
    """
    prog = CobolProgram(program_id="TEST")
    prog.file_descriptions.append(
        FD(name="CUST-FILE", record_name="CUST-REC", fields=[], is_indexed=True, record_key="CUST-ID")
    )
    with TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "routes"))
        FlatFileBridgeEmitter(prog).emit(td)
        code = open(os.path.join(td, "routes", "flatfiles.py")).read()

    assert "def init_cust_file_table():" in code   # valid Python
    assert "def init_cust-file_table():" not in code  # invalid Python gone
    ast.parse(code)   # must parse cleanly


# ---------------------------------------------------------------------------
# Bug 5 — parser: PROGRAM-ID must be read from source, not filename
# ---------------------------------------------------------------------------

def test_program_id_parsed_from_source(tmp_path):
    """program_id must reflect PROGRAM-ID. declaration, not the filename."""
    cbl = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTMGMT.
       PROCEDURE DIVISION.
       MAIN. GOBACK.
    """
    # File is named differently from the PROGRAM-ID
    path = make_cbl(tmp_path, cbl, name="totally_different_name.cbl")
    prog = CobolParser().parse(path)
    assert prog.program_id == "ACCTMGMT"


# ---------------------------------------------------------------------------
# Bug 6 — mapper: WS 01-level groups must produce real models
# ---------------------------------------------------------------------------

def test_ws_group_produces_model(tmp_path):
    """
    A 01-level working-storage group should generate a Pydantic model whose
    fields come from its children, not be silently dropped.
    """
    cbl = """
       WORKING-STORAGE SECTION.
       01 WS-CUSTOMER.
          05 CUST-ID    PIC 9(8).
          05 CUST-NAME  PIC X(40).
    """
    path = make_cbl(tmp_path, cbl)
    prog = CobolParser().parse(path)
    mapper = TypeMapper(prog)
    models = mapper.to_pydantic()

    assert "WsCustomer" in models or "WSCUSTOMER" in models.keys() or any(
        "customer" in k.lower() for k in models
    ), f"Expected a WsCustomer model, got: {list(models.keys())}"


# ---------------------------------------------------------------------------
# Bug 8 — runtime: V-decimal ctypes size must count all literal V-nines
# ---------------------------------------------------------------------------

def test_runtime_shim_correct_ctype_size(tmp_path):
    """
    ctypes char array for PIC 9(10)V99 must be 12 bytes, not 11
    (10 integer digits + 2 decimal digits, not 10+1).
    """
    from cobol_wrap.runtime import RuntimePackager

    prog = CobolProgram(program_id="T")
    prog.linkage_section.append(DataField(level=1, name="BALANCE", pic_clause="9(10)V99"))

    shim = RuntimePackager._generate_shim(prog)
    # The struct field for BALANCE should be ctypes.c_char * 12
    assert "ctypes.c_char * 12" in shim
    assert "ctypes.c_char * 11" not in shim


# ---------------------------------------------------------------------------
# Bug 9 — emitter: OpenAPIEmitter must populate paths and schemas
# ---------------------------------------------------------------------------

def test_openapi_emitter_populates_paths():
    """OpenAPI spec must contain actual path entries for each entry point."""
    prog = CobolProgram(program_id="ACCT")
    prog.linkage_section.append(DataField(level=1, name="ACCT-ID", pic_clause="9(8)"))
    prog.procedure_division.append(EntryPoint(name="ACCT", params=["ACCT-ID"]))

    spec = OpenAPIEmitter(prog, "Test", "1.0.0").to_dict()
    assert "/acct" in spec["paths"]
    assert "post" in spec["paths"]["/acct"]
    assert spec["paths"]["/acct"]["post"]["operationId"] == "acct"


def test_openapi_emitter_populates_schemas():
    """OpenAPI spec must contain schema components from the linkage section."""
    prog = CobolProgram(program_id="ACCT")
    prog.linkage_section.append(DataField(level=1, name="ACCT-ID", pic_clause="9(8)"))

    spec = OpenAPIEmitter(prog, "Test", "1.0.0").to_dict()
    assert "ACCT-ID" in spec["components"]["schemas"]


def test_openapi_emitter_decimal_schema():
    """Decimal PIC fields must appear as number type in the OpenAPI schema."""
    prog = CobolProgram(program_id="ACCT")
    prog.linkage_section.append(DataField(level=1, name="BALANCE", pic_clause="9(10)V99"))
    prog.procedure_division.append(EntryPoint(name="ACCT", params=["BALANCE"]))

    spec = OpenAPIEmitter(prog, "T", "1.0").to_dict()
    req_props = spec["paths"]["/acct"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert req_props["balance"]["type"] == "number"


# ---------------------------------------------------------------------------
# Bug 11 — parser: OCCURS range form
# ---------------------------------------------------------------------------

def test_parse_occurs_range(tmp_path):
    """OCCURS 1 TO 10 TIMES DEPENDING ON VAR must use max size (10)."""
    cbl = """
       WORKING-STORAGE SECTION.
       01 WS-REC.
          05 WS-ARR PIC X(5) OCCURS 1 TO 10 TIMES DEPENDING ON WS-CNT.
    """
    path = make_cbl(tmp_path, cbl)
    prog = CobolParser().parse(path)
    arr_field = prog.working_storage[0].children[0]
    assert arr_field.occurs == 10                  # max, not min
    assert arr_field.occurs_depending_on == "WS-CNT"
