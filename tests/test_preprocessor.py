import pytest
import os
from tempfile import NamedTemporaryFile, TemporaryDirectory
from cobol_wrap.preprocessor import CobolPreprocessor

def test_copybook_resolution():
    with TemporaryDirectory() as td:
        # Create a mock copybook
        cpy_path = os.path.join(td, "MOCKCPY.cpy")
        with open(cpy_path, "w") as f:
            f.write("       05 WS-IMPORTED PIC X(10).\n")
            
        cbl_path = os.path.join(td, "main.cbl")
        with open(cbl_path, "w") as f:
            f.write("       01 WS-MAIN.\n")
            f.write("           COPY MOCKCPY.\n")
            
        pre = CobolPreprocessor(copybook_dirs=[td])
        out_path = pre.process(cbl_path)
        
        with open(out_path, "r") as f:
            content = f.read()
            assert "05 WS-IMPORTED PIC X(10)." in content
            
def test_exec_sql_interception():
    with TemporaryDirectory() as td:
        cbl_path = os.path.join(td, "sql.cbl")
        with open(cbl_path, "w") as f:
            f.write("       EXEC SQL\n")
            f.write("           SELECT CUST_NAME INTO :WS-NAME FROM CUSTOMERS\n")
            f.write("       END-EXEC\n")
            
        pre = CobolPreprocessor()
        out_path = pre.process(cbl_path)
        
        # Verify the block was removed and replaced with a CALL hook
        with open(out_path, "r") as f:
            content = f.read()
            assert "EXEC SQL" not in content
            assert "CALL 'SQL-BRIDGE'" in content
            
        # Verify operation was logged
        assert len(pre.sql_operations) == 1
        assert "SELECT" in pre.sql_operations[0]["query"]
        assert "WS-NAME" in pre.sql_operations[0]["host_vars"]

def test_exec_cics_interception():
    with TemporaryDirectory() as td:
        cbl_path = os.path.join(td, "cics.cbl")
        with open(cbl_path, "w") as f:
            f.write("       EXEC CICS RECEIVE\n")
            f.write("           MAP('ACCTMAP') MAPSET('ACCTSET')\n")
            f.write("       END-EXEC\n")
            
        pre = CobolPreprocessor()
        out_path = pre.process(cbl_path)
        
        with open(out_path, "r") as f:
            content = f.read()
            assert "EXEC CICS" not in content
            assert "CALL 'CICS-BRIDGE'" in content
            
        assert len(pre.cics_operations) == 1
        assert "RECEIVE" in pre.cics_operations[0]["command"]
