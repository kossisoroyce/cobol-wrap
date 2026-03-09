import pytest
from cobol_wrap.ast import CobolProgram, DataField, EntryPoint, FD
from cobol_wrap.emitter import OpenAPIEmitter, ServerEmitter
from cobol_wrap.bridge import FlatFileBridgeEmitter
import tempfile
import ast

def test_openapi_spec():
    prog = CobolProgram(program_id="TEST")
    prog.procedure_division.append(EntryPoint(name="TEST-PROC", params=[]))
    
    emitter = OpenAPIEmitter(prog, "Test API", "1.0.0")
    spec = emitter.to_dict()
    
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "Test API"

def test_fastapi_server_generation():
    prog = CobolProgram(program_id="MOCKSERV")
    prog.procedure_division.append(EntryPoint(name="MOCK-PARA", params=[]))
    
    # Needs a mock models dict to pass to emitter init (though it recompiles)
    with tempfile.TemporaryDirectory() as td:
        emitter = ServerEmitter(prog, {}, "", flat_files=False)
        emitter.emit(td)
        
        with open(f"{td}/server.py", "r") as f:
            code = f.read()
            # Verify syntactically valid python
            ast.parse(code)
            assert "FastAPI" in code

def test_multiple_routes():
    prog = CobolProgram(program_id="MOCKSERV")
    prog.procedure_division.extend([
        EntryPoint(name="PARA1", params=[]),
        EntryPoint(name="PARA2", params=[])
    ])
    
    with tempfile.TemporaryDirectory() as td:
        emitter = ServerEmitter(prog, {}, "", flat_files=False)
        emitter.emit(td)
        
        with open(f"{td}/routes/procedure.py", "r") as f:
            code = f.read()
            # Verify routes generate 2 para handlers
            assert "@router.post('/para1')" in code
            assert "@router.post('/para2')" in code
            
def test_flatfile_bridge():
    prog = CobolProgram(program_id="MOCKSERV")
    prog.file_descriptions.append(FD(name="TEST-FD", record_name="TEST-REC", fields=[], is_indexed=True, record_key="KEY-ID"))
    
    with tempfile.TemporaryDirectory() as td:
        emitter = FlatFileBridgeEmitter(prog)
        import os
        os.makedirs(f"{td}/routes", exist_ok=True)
        emitter.emit(td)
        
        with open(f"{td}/routes/flatfiles.py", "r") as f:
            code = f.read()
            # Verify SQLite logic emitted for VSAM KSDS Mock
            assert "def init_test_fd_table():" in code   # hyphen → underscore (valid Python)
            assert "init_test_fd_table()" in code
            assert "CREATE TABLE IF NOT EXISTS records (KEY_ID TEXT PRIMARY KEY, data JSON)" in code
            assert "@router.post('/test-fd')" in code    # URL path keeps hyphens (HTTP convention)
            assert "@router.get('/test-fd')" in code
