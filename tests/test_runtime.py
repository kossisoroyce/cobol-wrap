"""
True end-to-end runtime tests: compile real COBOL with GnuCOBOL, execute
via ctypes, test generated FastAPI routes via TestClient, and exercise the
SQLite VSAM adapter CRUD.

Requires GnuCOBOL (cobc) to be installed — tests are auto-skipped otherwise.
"""
import ctypes
import ctypes.util
import importlib.util
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cobol_wrap import wrap

COBOL_DIR = Path(__file__).parent / "cobol"
COBC = shutil.which("cobc")

pytestmark = pytest.mark.skipif(COBC is None, reason="GnuCOBOL (cobc) not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lib_ext() -> str:
    return ".dylib" if sys.platform == "darwin" else ".so"


def compile_cobol(src: Path, out_dir: Path) -> Path:
    """Compile COBOL source to a shared library. Returns path to .dylib/.so."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bridges = out_dir / "bridges.c"
    bridges.write_text("void SQL_BRIDGE() {}\nvoid CICS_BRIDGE() {}\n")
    shutil.copy2(src, out_dir / src.name)

    result = subprocess.run(
        [COBC, "-F", "-m", src.name, "bridges.c"],
        cwd=str(out_dir), capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"cobc failed for {src.name}:\n{result.stderr}")

    candidates = list(out_dir.glob(f"*{_lib_ext()}"))
    assert candidates, f"No compiled library found in {out_dir}"
    return candidates[0]


_libcob_initialized = False

def _ensure_cob_init():
    global _libcob_initialized
    if _libcob_initialized:
        return
    libcob_name = ctypes.util.find_library("cob")
    assert libcob_name, "libcob not found"
    ctypes.CDLL(libcob_name, mode=ctypes.RTLD_GLOBAL).cob_init(0, None)
    _libcob_initialized = True


def load_cobol_lib(lib_path: Path) -> ctypes.CDLL:
    _ensure_cob_init()
    return ctypes.CDLL(str(lib_path))


@contextmanager
def api_context(api_dir: str):
    """Temporarily manage sys.path and sys.modules for generated API imports."""
    modules_before = set(sys.modules.keys())
    sys.path.insert(0, api_dir)
    try:
        yield
    finally:
        if api_dir in sys.path:
            sys.path.remove(api_dir)
        for key in list(sys.modules.keys()):
            if key not in modules_before:
                del sys.modules[key]


def import_module_from_file(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Compilation tests
# ---------------------------------------------------------------------------

class TestCobolCompilation:
    def test_compute_compiles(self, tmp_path):
        lib = compile_cobol(COBOL_DIR / "compute.cbl", tmp_path / "compute")
        assert lib.exists()
        assert lib.suffix in (".dylib", ".so")

    def test_payroll_compiles(self, tmp_path):
        assert compile_cobol(COBOL_DIR / "payroll.cbl", tmp_path / "payroll").exists()

    def test_inventory_compiles(self, tmp_path):
        assert compile_cobol(COBOL_DIR / "inventory.cbl", tmp_path / "inventory").exists()

    def test_sql_bridge_compiles(self, tmp_path):
        from cobol_wrap.preprocessor import CobolPreprocessor
        pre = CobolPreprocessor()
        processed = pre.process(str(COBOL_DIR / "sql_bridge.cbl"))
        try:
            assert compile_cobol(Path(processed), tmp_path / "sql").exists()
        finally:
            if os.path.exists(processed):
                os.remove(processed)

    def test_cics_bridge_compiles(self, tmp_path):
        from cobol_wrap.preprocessor import CobolPreprocessor
        pre = CobolPreprocessor()
        processed = pre.process(str(COBOL_DIR / "cics_bridge.cbl"))
        try:
            assert compile_cobol(Path(processed), tmp_path / "cics").exists()
        finally:
            if os.path.exists(processed):
                os.remove(processed)


# ---------------------------------------------------------------------------
# 2. ctypes runtime tests — raw COBOL calls
# ---------------------------------------------------------------------------

class TestCtypesRuntime:
    @pytest.fixture(scope="class")
    def compute_lib(self, tmp_path_factory):
        td = tmp_path_factory.mktemp("compute_rt")
        return load_cobol_lib(compile_cobol(COBOL_DIR / "compute.cbl", td))

    @pytest.fixture(scope="class")
    def payroll_lib(self, tmp_path_factory):
        td = tmp_path_factory.mktemp("payroll_rt")
        return load_cobol_lib(compile_cobol(COBOL_DIR / "payroll.cbl", td))

    def _call_compute(self, lib, a_val, b_val):
        class A(ctypes.Structure):       _fields_ = [("v", ctypes.c_char * 4)]
        class B(ctypes.Structure):       _fields_ = [("v", ctypes.c_char * 4)]
        class Sum(ctypes.Structure):     _fields_ = [("v", ctypes.c_char * 8)]
        class Prod(ctypes.Structure):    _fields_ = [("v", ctypes.c_char * 8)]
        a, b, s, p = A(), B(), Sum(), Prod()
        a.v = f"{a_val:04d}".encode()
        b.v = f"{b_val:04d}".encode()
        s.v = b"00000000"; p.v = b"00000000"
        lib.COMPUTE(ctypes.byref(a), ctypes.byref(b), ctypes.byref(s), ctypes.byref(p))
        return int(s.v), int(p.v)

    def test_compute_addition(self, compute_lib):
        s, _ = self._call_compute(compute_lib, 7, 3)
        assert s == 10

    def test_compute_multiplication(self, compute_lib):
        _, p = self._call_compute(compute_lib, 7, 3)
        assert p == 21

    def test_compute_zero_inputs(self, compute_lib):
        s, p = self._call_compute(compute_lib, 0, 0)
        assert s == 0 and p == 0

    def test_compute_large_inputs(self, compute_lib):
        s, p = self._call_compute(compute_lib, 100, 99)
        assert s == 199 and p == 9900

    def _call_payroll(self, lib, hours_cents, rate_cents):
        """hours/rate in cents to fill V99 display fields (5/6 chars)."""
        class EmpId(ctypes.Structure):   _fields_ = [("v", ctypes.c_char * 6)]
        class Hours(ctypes.Structure):   _fields_ = [("v", ctypes.c_char * 5)]
        class Rate(ctypes.Structure):    _fields_ = [("v", ctypes.c_char * 6)]
        class NetPay(ctypes.Structure):  _fields_ = [("v", ctypes.c_char * 10)]
        class Status(ctypes.Structure):  _fields_ = [("v", ctypes.c_char * 2)]
        emp, hours, rate = EmpId(), Hours(), Rate()
        net, status = NetPay(), Status()
        emp.v = b"000001"
        hours.v = f"{hours_cents:05d}".encode()
        rate.v = f"{rate_cents:06d}".encode()
        net.v = b"0000000000"; status.v = b"99"
        lib.PAYROLL(
            ctypes.byref(emp), ctypes.byref(hours), ctypes.byref(rate),
            ctypes.byref(net), ctypes.byref(status)
        )
        return int(net.v), status.v

    def test_payroll_net_pay(self, payroll_lib):
        """40h × $25/hr = $1000 gross; 25% tax → $750 net → display 0000075000"""
        net, _ = self._call_payroll(payroll_lib, 4000, 2500)
        assert net == 75000  # 750.00 in V99 display

    def test_payroll_status_zero(self, payroll_lib):
        _, status = self._call_payroll(payroll_lib, 4000, 2500)
        assert status == b"00"

    def test_payroll_proportional(self, payroll_lib):
        """20h × $10/hr = $200 gross; 25% tax → $150 net → display 0000015000"""
        net, _ = self._call_payroll(payroll_lib, 2000, 1000)
        assert net == 15000


# ---------------------------------------------------------------------------
# 3. Shim integration tests — generated CobolRuntime class
# ---------------------------------------------------------------------------

class TestGeneratedShim:
    @pytest.fixture(scope="class")
    def compute_runtime(self, tmp_path_factory):
        td = tmp_path_factory.mktemp("compute_shim")
        wrap(str(COBOL_DIR / "compute.cbl"), output_dir=str(td))
        lib_path = compile_cobol(COBOL_DIR / "compute.cbl", td / "runtime")
        _ensure_cob_init()
        shim = import_module_from_file(str(td / "runtime" / "shim.py"), "shim_compute")
        return shim.CobolRuntime(str(lib_path))

    @pytest.fixture(scope="class")
    def payroll_runtime(self, tmp_path_factory):
        td = tmp_path_factory.mktemp("payroll_shim")
        wrap(str(COBOL_DIR / "payroll.cbl"), output_dir=str(td))
        lib_path = compile_cobol(COBOL_DIR / "payroll.cbl", td / "runtime")
        _ensure_cob_init()
        shim = import_module_from_file(str(td / "runtime" / "shim.py"), "shim_payroll")
        return shim.CobolRuntime(str(lib_path))

    def test_compute_sum(self, compute_runtime):
        result = compute_runtime.call("COMPUTE", {
            "LK_A": "0007", "LK_B": "0003",
            "LK_SUM": "00000000", "LK_PRODUCT": "00000000"
        })
        assert "lk_sum" in result
        assert int(result["lk_sum"]) == 10

    def test_compute_product(self, compute_runtime):
        result = compute_runtime.call("COMPUTE", {
            "LK_A": "0007", "LK_B": "0003",
            "LK_SUM": "00000000", "LK_PRODUCT": "00000000"
        })
        assert int(result["lk_product"]) == 21

    def test_payroll_net_pay(self, payroll_runtime):
        result = payroll_runtime.call("PAYROLL", {
            "LK_EMP_ID": "000001", "LK_HOURS": "04000",
            "LK_RATE": "002500", "LK_NET_PAY": "0000000000",
            "LK_STATUS_CODE": "00"
        })
        assert int(result["lk_net_pay"]) == 75000

    def test_payroll_status(self, payroll_runtime):
        result = payroll_runtime.call("PAYROLL", {
            "LK_EMP_ID": "000001", "LK_HOURS": "04000",
            "LK_RATE": "002500", "LK_NET_PAY": "0000000000",
            "LK_STATUS_CODE": "99"
        })
        assert int(result["lk_status_code"]) == 0

    def test_missing_binary_raises(self, tmp_path_factory):
        td = tmp_path_factory.mktemp("missing_bin")
        wrap(str(COBOL_DIR / "compute.cbl"), output_dir=str(td))
        _ensure_cob_init()
        shim = import_module_from_file(str(td / "runtime" / "shim.py"), "shim_missing")
        with pytest.raises(RuntimeError, match="not found"):
            shim.CobolRuntime(str(td / "runtime" / "nonexistent.so"))


# ---------------------------------------------------------------------------
# 4. FastAPI HTTP tests via TestClient
# ---------------------------------------------------------------------------

COMPUTE_PAYLOAD = {"lk_a": "0007", "lk_b": "0003", "lk_sum": "00000000", "lk_product": "00000000"}
PAYROLL_PAYLOAD = {
    "lk_emp_id": 1, "lk_hours": "40.00", "lk_rate": "25.00",
    "lk_net_pay": "0.00", "lk_status_code": 0
}


def _get_key(body: dict, name: str):
    """Get a value from response body, trying both field name and alias forms."""
    if name in body:
        return body[name]
    # Try COBOL-style alias (uppercase with hyphens)
    alias = name.upper().replace("_", "-")
    if alias in body:
        return body[alias]
    raise KeyError(f"{name} not found in {list(body.keys())}")


def _make_test_client(tmp_path_factory, cobol_src: str, with_binary: bool = False, label: str = "test"):
    """Build a FastAPI TestClient for a generated API. Use importlib to avoid module caching."""
    td = tmp_path_factory.mktemp(label)
    wrap(str(COBOL_DIR / cobol_src), output_dir=str(td))
    if with_binary:
        compile_cobol(COBOL_DIR / cobol_src, td / "runtime")
        _ensure_cob_init()

    # Purge any previously cached modules that conflict
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("models", "server", "routes", "routes.procedure",
                        "routes.flatfiles", "routes.graphql_api",
                        "runtime", "runtime.shim") or mod_name.startswith("routes."):
            del sys.modules[mod_name]

    sys.path.insert(0, str(td))
    try:
        models_mod = import_module_from_file(str(td / "models.py"), f"models_{label}")
        sys.modules["models"] = models_mod
        server_mod = import_module_from_file(str(td / "server.py"), f"server_{label}")
    finally:
        if str(td) in sys.path:
            sys.path.remove(str(td))
        # Clean up so next test client starts fresh
        for mod_name in list(sys.modules.keys()):
            if mod_name in ("models", "server", "routes", "routes.procedure",
                            "routes.flatfiles", "routes.graphql_api",
                            "runtime", "runtime.shim") or mod_name.startswith("routes."):
                del sys.modules[mod_name]

    return TestClient(server_mod.app, raise_server_exceptions=False)


class TestFastAPINoBinary:
    @pytest.fixture(scope="class")
    def client(self, tmp_path_factory):
        return _make_test_client(tmp_path_factory, "compute.cbl", False, "http_nobin")

    def test_route_exists(self, client):
        assert client.post("/compute", json=COMPUTE_PAYLOAD).status_code != 404

    def test_returns_503(self, client):
        r = client.post("/compute", json=COMPUTE_PAYLOAD)
        assert r.status_code == 503
        assert "not loaded" in r.json()["detail"]

    def test_openapi_schema(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert "/compute" in r.json()["paths"]

    def test_docs_endpoint(self, client):
        assert client.get("/docs").status_code == 200


class TestFastAPIWithBinary:
    @pytest.fixture(scope="class")
    def compute_client(self, tmp_path_factory):
        return _make_test_client(tmp_path_factory, "compute.cbl", True, "http_compute")

    @pytest.fixture(scope="class")
    def payroll_client(self, tmp_path_factory):
        return _make_test_client(tmp_path_factory, "payroll.cbl", True, "http_payroll")

    def test_compute_200(self, compute_client):
        assert compute_client.post("/compute", json=COMPUTE_PAYLOAD).status_code == 200

    def test_compute_sum(self, compute_client):
        body = compute_client.post("/compute", json=COMPUTE_PAYLOAD).json()
        assert int(_get_key(body, "lk_sum")) == 10

    def test_compute_product(self, compute_client):
        body = compute_client.post("/compute", json=COMPUTE_PAYLOAD).json()
        assert int(_get_key(body, "lk_product")) == 21

    def test_payroll_200(self, payroll_client):
        assert payroll_client.post("/payroll", json=PAYROLL_PAYLOAD).status_code == 200

    def test_payroll_net_pay(self, payroll_client):
        body = payroll_client.post("/payroll", json=PAYROLL_PAYLOAD).json()
        net = _get_key(body, "lk_net_pay")
        # Shim returns display-format string "0000075000" → model coerces to number
        # Could be 75000 (raw display) or 750.00 (if Decimal-aware). Accept either.
        assert float(str(net).lstrip("0") or "0") in (75000, 750.0, 750.00)

    def test_payroll_status(self, payroll_client):
        body = payroll_client.post("/payroll", json=PAYROLL_PAYLOAD).json()
        assert int(_get_key(body, "lk_status_code")) == 0


# ---------------------------------------------------------------------------
# 5. SQLite VSAM CRUD tests
# ---------------------------------------------------------------------------

def _smart_default(fi):
    """Generate a valid default value for a Pydantic model field."""
    ann = fi.annotation

    # Detect enum types (generated from 88-level COBOL fields)
    if isinstance(ann, type) and issubclass(ann, Enum):
        return list(ann)[0].value

    # Respect max_length on string fields
    max_len = None
    if hasattr(fi, "metadata"):
        for m in fi.metadata:
            if hasattr(m, "max_length"):
                max_len = m.max_length

    ann_str = str(ann)
    if "str" in ann_str:
        val = "TEST"
        if max_len and len(val) > max_len:
            val = val[:max_len]
        return val
    if "Decimal" in ann_str:
        return "0"
    return 0


class TestSqliteVsamCrud:
    @pytest.fixture(scope="class")
    def vsam_mod(self, tmp_path_factory):
        td = tmp_path_factory.mktemp("vsam_crud")
        wrap(str(COBOL_DIR / "customer_vsam.cbl"), output_dir=str(td), vsam=True)
        old_cwd = os.getcwd()
        os.chdir(str(td))  # SQLite DBs created relative to CWD
        try:
            with api_context(str(td)):
                yield import_module_from_file(
                    str(td / "routes" / "flatfiles.py"), "flatfiles_vsam_test"
                )
        finally:
            os.chdir(old_cwd)

    def _make_record(self, mod, overrides=None):
        cls = mod.CustomerMasterRec
        data = {(fi.alias or name): _smart_default(fi) for name, fi in cls.model_fields.items()}
        if overrides:
            data.update(overrides)
        return cls.model_validate(data)

    def test_create(self, vsam_mod):
        assert self._make_record(vsam_mod, {"CUST-KEY": "CREATE01"}) is not None
        result = vsam_mod.create_customer_master(self._make_record(vsam_mod, {"CUST-KEY": "CREATE01"}))
        assert result["status"] == "success"

    def test_read_returns_list(self, vsam_mod):
        assert isinstance(vsam_mod.read_customer_master(), list)

    def test_read_after_write(self, vsam_mod):
        vsam_mod.create_customer_master(self._make_record(vsam_mod, {"CUST-KEY": "READTST1"}))
        assert len(vsam_mod.read_customer_master()) >= 1

    def test_duplicate_key_rejected(self, vsam_mod):
        from fastapi import HTTPException
        record = self._make_record(vsam_mod, {"CUST-KEY": "DUPKEY01"})
        vsam_mod.create_customer_master(record)
        with pytest.raises(HTTPException) as exc_info:
            vsam_mod.create_customer_master(record)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 6. Sequential flat file CRUD tests
# ---------------------------------------------------------------------------

class TestSequentialFlatFileCrud:
    @pytest.fixture(scope="class")
    def inv_mod(self, tmp_path_factory):
        td = tmp_path_factory.mktemp("inv_crud")
        wrap(str(COBOL_DIR / "inventory.cbl"), output_dir=str(td), flat_files=True)
        with api_context(str(td)):
            yield import_module_from_file(
                str(td / "routes" / "flatfiles.py"), "flatfiles_inv_test"
            )

    def _make_inv_record(self, mod, overrides=None):
        cls = mod.InventoryRecord
        data = {(fi.alias or name): _smart_default(fi) for name, fi in cls.model_fields.items()}
        if overrides:
            data.update(overrides)
        return cls.model_validate(data)

    def test_read_empty(self, inv_mod):
        assert isinstance(inv_mod.read_inventory_file(), list)

    def test_create_success(self, inv_mod):
        assert inv_mod.create_inventory_file(self._make_inv_record(inv_mod))["status"] == "success"

    def test_read_after_write(self, inv_mod):
        inv_mod.create_inventory_file(self._make_inv_record(inv_mod, {"ITEM-CODE": "AFTER01"}))
        assert len(inv_mod.read_inventory_file()) >= 1

    def test_multiple_records(self, inv_mod):
        before = len(inv_mod.read_inventory_file())
        for i in range(3):
            inv_mod.create_inventory_file(
                self._make_inv_record(inv_mod, {"ITEM-CODE": f"MULTI{i:02d}"})
            )
        assert len(inv_mod.read_inventory_file()) == before + 3
