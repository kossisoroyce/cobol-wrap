"""
End-to-end pipeline tests using real COBOL programs.
Verifies every stage: Preprocessor → Parser → Mapper → Emitter → Generated output validity.
"""
import ast
import os
import yaml
import pytest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from cobol_wrap.parser import CobolParser
from cobol_wrap.preprocessor import CobolPreprocessor
from cobol_wrap.mapper import TypeMapper
from cobol_wrap.emitter import OpenAPIEmitter, ServerEmitter
from cobol_wrap.bridge import FlatFileBridgeEmitter
from cobol_wrap import wrap

COBOL_DIR = Path(__file__).parent / "cobol"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(filename: str, copybook_dirs=None):
    """Preprocess then parse a COBOL file; return (program, preprocessor)."""
    pre = CobolPreprocessor(copybook_dirs=copybook_dirs or [])
    processed = pre.process(str(COBOL_DIR / filename))
    prog = CobolParser().parse(processed)
    if os.path.exists(processed):
        os.remove(processed)
    return prog, pre


def assert_valid_python(code: str, label: str = ""):
    try:
        ast.parse(code)
    except SyntaxError as e:
        pytest.fail(f"SyntaxError in generated Python ({label}):\n{e}\n\nCode:\n{code[:800]}")


def assert_valid_yaml(text: str, label: str = ""):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        pytest.fail(f"YAML error ({label}): {e}")


def all_files_valid_python(output_dir: str, files):
    for fname in files:
        path = os.path.join(output_dir, fname)
        assert os.path.exists(path), f"Missing expected file: {fname}"
        assert_valid_python(open(path).read(), fname)


# ===========================================================================
# payroll.cbl — all COBOL data types
# ===========================================================================

class TestPayrollPipeline:
    def test_parse_program_id(self):
        prog, _ = parse("payroll.cbl")
        assert prog.program_id == "PAYROLL"

    def test_parse_linkage_params(self):
        prog, _ = parse("payroll.cbl")
        assert len(prog.procedure_division) == 1
        ep = prog.procedure_division[0]
        assert "LK-EMP-ID" in ep.params
        assert "LK-NET-PAY" in ep.params
        assert "LK-STATUS-CODE" in ep.params

    def test_parse_ws_groups(self):
        prog, _ = parse("payroll.cbl")
        ws_names = [f.name for f in prog.working_storage]
        assert "WS-EMPLOYEE-DATA" in ws_names
        assert "WS-TAX-TABLE" in ws_names

    def test_parse_comp3_fields(self):
        prog, _ = parse("payroll.cbl")
        emp = next(f for f in prog.working_storage if f.name == "WS-EMPLOYEE-DATA")
        rate = next(c for c in emp.children if c.name == "WS-HOURLY-RATE")
        assert rate.is_comp3 is True

    def test_parse_occurs(self):
        prog, _ = parse("payroll.cbl")
        tax = next(f for f in prog.working_storage if f.name == "WS-TAX-TABLE")
        bracket = next(c for c in tax.children if c.name == "WS-TAX-BRACKET")
        assert bracket.occurs == 5

    def test_parse_88_status_values(self):
        prog, _ = parse("payroll.cbl")
        emp = next(f for f in prog.working_storage if f.name == "WS-EMPLOYEE-DATA")
        status = next(c for c in emp.children if c.name == "WS-STATUS")
        assert "F" in status.enum_values
        assert "P" in status.enum_values
        assert "C" in status.enum_values

    def test_comp3_maps_to_decimal(self):
        prog, _ = parse("payroll.cbl")
        emp = next(f for f in prog.working_storage if f.name == "WS-EMPLOYEE-DATA")
        gross = next(c for c in emp.children if c.name == "WS-GROSS-PAY")
        t, _ = TypeMapper(prog)._map_field(gross)
        assert t == Decimal

    def test_v99_linkage_decimal_places(self):
        """LK-HOURS PIC 9(3)V99 → decimal_places=2 not 9."""
        prog, _ = parse("payroll.cbl")
        lk_hours = next(f for f in prog.linkage_section if f.name == "LK-HOURS")
        t, f = TypeMapper(prog)._map_field(lk_hours)
        assert t == Decimal
        dec = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
        assert dec is not None
        assert dec.decimal_places == 2

    def test_full_pipeline_valid_python(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "payroll.cbl"), output_dir=td)
            all_files_valid_python(td, [
                "server.py", "models.py",
                "routes/procedure.py", "runtime/shim.py"
            ])

    def test_full_pipeline_openapi_has_path(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "payroll.cbl"), output_dir=td)
            spec = assert_valid_yaml(open(os.path.join(td, "openapi.yaml")).read())
            assert "/payroll" in spec["paths"]
            op = spec["paths"]["/payroll"]["post"]
            assert op["operationId"] == "payroll"

    def test_procedure_returns_kwargs(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "payroll.cbl"), output_dir=td)
            proc = open(os.path.join(td, "routes/procedure.py")).read()
            assert "return result" in proc

    def test_request_model_fields(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "payroll.cbl"), output_dir=td)
            models_py = open(os.path.join(td, "models.py")).read()
            assert "class PayrollRequest(BaseModel):" in models_py
            assert "lk_emp_id" in models_py
            assert "lk_net_pay" in models_py
            assert "decimal_places=2" in models_py


# ===========================================================================
# inventory.cbl — sequential flat file FD
# ===========================================================================

class TestInventoryFlatFilePipeline:
    def test_fd_record_name_from_source(self):
        prog, _ = parse("inventory.cbl")
        fd = prog.file_descriptions[0]
        assert fd.name == "INVENTORY-FILE"
        assert fd.record_name == "INVENTORY-RECORD"  # actual 01-level name
        assert fd.is_indexed is False

    def test_fd_fields_via_children(self):
        prog, _ = parse("inventory.cbl")
        fd = prog.file_descriptions[0]
        root = fd.fields[0]
        names = [c.name for c in root.children]
        assert "ITEM-CODE" in names
        assert "UNIT-PRICE" in names
        assert "ITEM-STATUS" in names

    def test_ws_not_in_fd(self):
        prog, _ = parse("inventory.cbl")
        fd = prog.file_descriptions[0]
        all_fd = [f.name for f in fd.fields] + [c.name for f in fd.fields for c in f.children]
        assert "WS-TOTALS" not in all_fd
        assert "WS-EOF-FLAG" not in all_fd

    def test_88_on_fd_field(self):
        prog, _ = parse("inventory.cbl")
        root = prog.file_descriptions[0].fields[0]
        status = next(c for c in root.children if c.name == "ITEM-STATUS")
        assert "A" in status.enum_values
        assert "D" in status.enum_values

    def test_mapper_generates_inventory_record_model(self):
        prog, _ = parse("inventory.cbl")
        models = TypeMapper(prog).to_pydantic()
        assert "InventoryRecord" in models
        model = models["InventoryRecord"]
        assert "item_code" in model.model_fields
        assert "unit_price" in model.model_fields

    def test_unit_price_decimal_places(self):
        """UNIT-PRICE PIC 9(6)V99 COMP-3 → decimal_places=2."""
        prog, _ = parse("inventory.cbl")
        root = prog.file_descriptions[0].fields[0]
        price = next(c for c in root.children if c.name == "UNIT-PRICE")
        t, f = TypeMapper(prog)._map_field(price)
        assert t == Decimal
        dec = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
        assert dec.decimal_places == 2

    def test_flat_file_bridge_valid_python(self):
        prog, _ = parse("inventory.cbl")
        with TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "routes"))
            FlatFileBridgeEmitter(prog).emit(td)
            code = open(os.path.join(td, "routes/flatfiles.py")).read()
            assert_valid_python(code, "inventory flatfiles.py")
            assert "@router.post('/inventory-file')" in code
            assert "@router.get('/inventory-file')" in code
            assert "def create_inventory_file" in code
            assert "InventoryRecord" in code

    def test_full_pipeline_with_flat_files(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "inventory.cbl"), output_dir=td, flat_files=True)
            all_files_valid_python(td, [
                "server.py", "models.py",
                "routes/procedure.py", "routes/flatfiles.py"
            ])

    def test_openapi_includes_flat_file_path(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "inventory.cbl"), output_dir=td, flat_files=True)
            spec = yaml.safe_load(open(os.path.join(td, "openapi.yaml")).read())
            assert "/inventory-file" in spec["paths"]
            assert "get" in spec["paths"]["/inventory-file"]
            assert "post" in spec["paths"]["/inventory-file"]


# ===========================================================================
# customer_vsam.cbl — VSAM indexed file
# ===========================================================================

class TestVsamPipeline:
    def test_parse_vsam_indexed_flag(self):
        prog, _ = parse("customer_vsam.cbl")
        fd = prog.file_descriptions[0]
        assert fd.name == "CUSTOMER-MASTER"
        assert fd.is_indexed is True

    def test_parse_vsam_record_key(self):
        prog, _ = parse("customer_vsam.cbl")
        fd = prog.file_descriptions[0]
        assert fd.record_key == "CUST-KEY"

    def test_vsam_fd_record_name(self):
        prog, _ = parse("customer_vsam.cbl")
        fd = prog.file_descriptions[0]
        assert fd.record_name == "CUSTOMER-MASTER-REC"

    def test_vsam_model_generated(self):
        prog, _ = parse("customer_vsam.cbl")
        models = TypeMapper(prog).to_pydantic()
        assert "CustomerMasterRec" in models

    def test_vsam_bridge_uses_sqlite(self):
        prog, _ = parse("customer_vsam.cbl")
        with TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "routes"))
            FlatFileBridgeEmitter(prog).emit(td)
            code = open(os.path.join(td, "routes/flatfiles.py")).read()
            assert_valid_python(code, "vsam flatfiles.py")
            assert "sqlite3" in code
            assert "CREATE TABLE IF NOT EXISTS" in code
            assert "CUST_KEY" in code

    def test_vsam_balance_decimal(self):
        prog, _ = parse("customer_vsam.cbl")
        root = prog.file_descriptions[0].fields[0]
        balance = next(c for c in root.children if c.name == "CUST-BALANCE")
        t, f = TypeMapper(prog)._map_field(balance)
        assert t == Decimal
        dec = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
        assert dec.decimal_places == 2

    def test_full_pipeline_vsam(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "customer_vsam.cbl"), output_dir=td, vsam=True)
            all_files_valid_python(td, [
                "server.py", "models.py",
                "routes/procedure.py", "routes/flatfiles.py"
            ])


# ===========================================================================
# data_types.cbl — comprehensive type coverage
# ===========================================================================

class TestDataTypesCoverage:
    def test_large_integer_bounds(self):
        prog, _ = parse("data_types.cbl")
        ws_num = next(f for f in prog.working_storage if f.name == "WS-NUMERIC-TYPES")
        large = next(c for c in ws_num.children if c.name == "WS-LARGE-INT")
        t, f = TypeMapper(prog)._map_field(large)
        assert t == int
        le = next((m for m in f.metadata if hasattr(m, "le")), None)
        assert le.le == 10**18 - 1

    def test_v99_decimal_places(self):
        prog, _ = parse("data_types.cbl")
        ws_num = next(f for f in prog.working_storage if f.name == "WS-NUMERIC-TYPES")
        dec_v99 = next(c for c in ws_num.children if c.name == "WS-DECIMAL-V99")
        t, f = TypeMapper(prog)._map_field(dec_v99)
        assert t == Decimal
        dec = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
        assert dec.decimal_places == 2
        assert dec.max_digits == 12

    def test_v9_parenthesized_decimal_places(self):
        prog, _ = parse("data_types.cbl")
        ws_num = next(f for f in prog.working_storage if f.name == "WS-NUMERIC-TYPES")
        dec_v9_2 = next(c for c in ws_num.children if c.name == "WS-DECIMAL-V9-2")
        t, f = TypeMapper(prog)._map_field(dec_v9_2)
        assert t == Decimal
        dec = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
        assert dec.decimal_places == 2

    def test_redefines_field(self):
        prog, _ = parse("data_types.cbl")
        redef = next(f for f in prog.working_storage if f.name == "WS-REDEFINES-NUM")
        assert redef.redefines == "WS-REDEFINES-BASE"

    def test_fixed_occurs(self):
        prog, _ = parse("data_types.cbl")
        grp = next(f for f in prog.working_storage if f.name == "WS-OCCURS-EXAMPLE")
        arr = next(c for c in grp.children if c.name == "WS-FIXED-ARR")
        assert arr.occurs == 10

    def test_range_occurs_uses_max(self):
        prog, _ = parse("data_types.cbl")
        grp = next(f for f in prog.working_storage if f.name == "WS-OCCURS-DEP")
        dyn = next(c for c in grp.children if c.name == "WS-DYN-ARR")
        assert dyn.occurs == 20          # max, not min
        assert dyn.occurs_depending_on == "WS-COUNT"

    def test_88_multivalue_enum(self):
        prog, _ = parse("data_types.cbl")
        status = next(f for f in prog.working_storage if f.name == "WS-STATUS-CODE")
        assert "00" in status.enum_values
        assert "99" in status.enum_values

    def test_comp_binary_mapped(self):
        prog, _ = parse("data_types.cbl")
        ws_num = next(f for f in prog.working_storage if f.name == "WS-NUMERIC-TYPES")
        comp_bin = next(c for c in ws_num.children if c.name == "WS-COMP-BIN")
        assert comp_bin.is_comp is True

    def test_full_pipeline_all_types(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "data_types.cbl"), output_dir=td)
            all_files_valid_python(td, ["server.py", "models.py", "routes/procedure.py"])
            spec = yaml.safe_load(open(os.path.join(td, "openapi.yaml")).read())
            assert "/datatypes" in spec["paths"]

    def test_models_py_has_decimal_types(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "data_types.cbl"), output_dir=td)
            models_py = open(os.path.join(td, "models.py")).read()
            assert "Decimal" in models_py
            assert "decimal_places=2" in models_py


# ===========================================================================
# sql_bridge.cbl — EXEC SQL interception
# ===========================================================================

class TestSqlBridgePipeline:
    def test_sql_blocks_intercepted(self):
        _, pre = parse("sql_bridge.cbl")
        assert len(pre.sql_operations) == 1
        op = pre.sql_operations[0]
        assert "SELECT" in op["query"]
        assert "WS-ACCOUNT-BALANCE" in op["host_vars"]
        assert "LK-ACCOUNT-ID" in op["host_vars"]

    def test_exec_sql_removed_from_source(self):
        pre = CobolPreprocessor()
        processed = pre.process(str(COBOL_DIR / "sql_bridge.cbl"))
        content = open(processed).read().upper()
        os.remove(processed)
        assert "EXEC SQL" not in content
        assert "CALL 'SQL-BRIDGE'" in content

    def test_full_pipeline_sql_program(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "sql_bridge.cbl"), output_dir=td)
            all_files_valid_python(td, ["server.py", "models.py", "routes/procedure.py"])

    def test_procedure_route_generated_for_sql_program(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "sql_bridge.cbl"), output_dir=td)
            proc = open(os.path.join(td, "routes/procedure.py")).read()
            assert "@router.post('/dbquery')" in proc


# ===========================================================================
# cics_bridge.cbl — EXEC CICS interception
# ===========================================================================

class TestCicsBridgePipeline:
    def test_cics_blocks_intercepted(self):
        _, pre = parse("cics_bridge.cbl")
        # Two CICS blocks: RECEIVE and RETURN
        assert len(pre.cics_operations) >= 1
        assert any("RECEIVE" in op["command"] for op in pre.cics_operations)

    def test_exec_cics_removed(self):
        pre = CobolPreprocessor()
        processed = pre.process(str(COBOL_DIR / "cics_bridge.cbl"))
        content = open(processed).read().upper()
        os.remove(processed)
        assert "EXEC CICS" not in content
        assert "CALL 'CICS-BRIDGE'" in content

    def test_full_pipeline_cics(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "cics_bridge.cbl"), output_dir=td)
            all_files_valid_python(td, ["server.py", "models.py", "routes/procedure.py"])

    def test_cics_openapi_path(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "cics_bridge.cbl"), output_dir=td)
            spec = yaml.safe_load(open(os.path.join(td, "openapi.yaml")).read())
            assert "/mapproc" in spec["paths"]


# ===========================================================================
# with_copy.cbl — COPY copybook resolution
# ===========================================================================

class TestCopybookPipeline:
    COPYBOOK_DIR = str(COBOL_DIR / "copybooks")

    def test_copybook_fields_inlined(self):
        pre = CobolPreprocessor(copybook_dirs=[self.COPYBOOK_DIR])
        processed = pre.process(str(COBOL_DIR / "with_copy.cbl"))
        content = open(processed).read()
        os.remove(processed)
        assert "ADDR-LINE1" in content
        assert "ADDR-STATE" in content
        assert "COPY ADDRESS" not in content.upper()

    def test_parsed_with_copybook_fields(self):
        pre = CobolPreprocessor(copybook_dirs=[self.COPYBOOK_DIR])
        processed = pre.process(str(COBOL_DIR / "with_copy.cbl"))
        prog = CobolParser().parse(processed)
        os.remove(processed)
        assert prog.program_id == "ADDRBOOK"
        contact = next(f for f in prog.working_storage if f.name == "WS-CONTACT")
        names = [c.name for c in contact.children]
        assert "CONTACT-ID" in names
        assert "ADDR-LINE1" in names
        assert "ADDR-STATE" in names
        assert "CONTACT-PHONE" in names

    def test_full_pipeline_with_copybook(self):
        pre = CobolPreprocessor(copybook_dirs=[self.COPYBOOK_DIR])
        processed = pre.process(str(COBOL_DIR / "with_copy.cbl"))
        with TemporaryDirectory() as td:
            wrap(processed, output_dir=td)
            if os.path.exists(processed):
                os.remove(processed)
            all_files_valid_python(td, ["server.py", "models.py"])


# ===========================================================================
# ACCTMGMT.cbl — reference program regression
# ===========================================================================

class TestAcctmgmtRegression:
    ACCTMGMT = Path(__file__).parent.parent / "examples" / "ACCTMGMT.cbl"

    def test_parse_program_id(self):
        prog = CobolParser().parse(str(self.ACCTMGMT))
        assert prog.program_id == "ACCTMGMT"

    def test_fd_record_name_actual(self):
        prog = CobolParser().parse(str(self.ACCTMGMT))
        fd = prog.file_descriptions[0]
        assert fd.name == "CUSTOMER-FILE"
        assert fd.record_name == "CUSTOMER-RECORD"

    def test_ws_not_in_fd(self):
        prog = CobolParser().parse(str(self.ACCTMGMT))
        assert len(prog.working_storage) == 1
        assert prog.working_storage[0].name == "WS-TEMP-VAR"

    def test_linkage_params(self):
        prog = CobolParser().parse(str(self.ACCTMGMT))
        ep = prog.procedure_division[0]
        assert "ACCT-ID" in ep.params
        assert "ACCT-BALANCE" in ep.params
        assert "RETURN-CODE" in ep.params

    def test_customer_record_model_fields(self):
        prog = CobolParser().parse(str(self.ACCTMGMT))
        models = TypeMapper(prog).to_pydantic()
        assert "CustomerRecord" in models
        m = models["CustomerRecord"]
        assert "cust_id" in m.model_fields
        assert "cust_name" in m.model_fields
        assert "cust_balance" in m.model_fields

    def test_acct_balance_v99_correct_decimal(self):
        prog = CobolParser().parse(str(self.ACCTMGMT))
        fd = prog.file_descriptions[0]
        root = fd.fields[0]
        bal = next(c for c in root.children if c.name == "CUST-BALANCE")
        t, f = TypeMapper(prog)._map_field(bal)
        assert t == Decimal
        dec = next((m for m in f.metadata if hasattr(m, "decimal_places")), None)
        assert dec.decimal_places == 2
        assert dec.max_digits == 12

    def test_full_pipeline_all_outputs_valid(self):
        with TemporaryDirectory() as td:
            wrap(str(self.ACCTMGMT), output_dir=td, flat_files=True)
            all_files_valid_python(td, [
                "server.py", "models.py",
                "routes/procedure.py", "routes/flatfiles.py",
                "runtime/shim.py"
            ])

    def test_openapi_has_both_paths(self):
        with TemporaryDirectory() as td:
            wrap(str(self.ACCTMGMT), output_dir=td, flat_files=True)
            spec = yaml.safe_load(open(os.path.join(td, "openapi.yaml")).read())
            assert "/acctmgmt" in spec["paths"]
            assert "/customer-file" in spec["paths"]

    def test_openapi_has_schemas(self):
        with TemporaryDirectory() as td:
            wrap(str(self.ACCTMGMT), output_dir=td, flat_files=True)
            spec = yaml.safe_load(open(os.path.join(td, "openapi.yaml")).read())
            assert len(spec["components"]["schemas"]) > 0

    def test_procedure_uses_kwargs_unpack(self):
        with TemporaryDirectory() as td:
            wrap(str(self.ACCTMGMT), output_dir=td, flat_files=True)
            proc = open(os.path.join(td, "routes/procedure.py")).read()
            assert "return result" in proc

    def test_models_py_has_correct_decimal(self):
        with TemporaryDirectory() as td:
            wrap(str(self.ACCTMGMT), output_dir=td, flat_files=True)
            models_py = open(os.path.join(td, "models.py")).read()
            assert "Decimal" in models_py
            assert "decimal_places=2" in models_py

    def test_runtime_shim_has_real_ctypes(self):
        with TemporaryDirectory() as td:
            wrap(str(self.ACCTMGMT), output_dir=td, flat_files=True)
            shim = open(os.path.join(td, "runtime/shim.py")).read()
            assert_valid_python(shim, "shim.py")
            assert "ctypes.CDLL" in shim
            assert "def call(" in shim
            # Must NOT be the old mock stub
            assert "mock response" not in shim.lower()

    def test_cobol_source_copied_to_runtime(self):
        with TemporaryDirectory() as td:
            wrap(str(self.ACCTMGMT), output_dir=td, flat_files=True)
            assert os.path.exists(os.path.join(td, "runtime", "acctmgmt.cbl"))


# ===========================================================================
# GraphQL emission — end-to-end
# ===========================================================================

class TestGraphQLEmission:
    def test_graphql_for_payroll(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "payroll.cbl"), output_dir=td, graphql=True)
            gql = open(os.path.join(td, "routes/graphql_api.py")).read()
            assert_valid_python(gql, "graphql_api.py")
            assert "import strawberry" in gql
            assert "class Query:" in gql
            assert "class Mutation:" in gql


# ===========================================================================
# Kafka streaming emission — end-to-end
# ===========================================================================

class TestKafkaEmission:
    def test_kafka_for_payroll(self):
        with TemporaryDirectory() as td:
            wrap(str(COBOL_DIR / "payroll.cbl"), output_dir=td, kafka=True)
            kafka = open(os.path.join(td, "routes/kafka_consumers.py")).read()
            assert_valid_python(kafka, "kafka_consumers.py")
            assert "KafkaBroker" in kafka
            assert "cobol.payroll" in kafka
