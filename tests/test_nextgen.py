import pytest
import os
from tempfile import TemporaryDirectory
from cobol_wrap import wrap
from cobol_wrap.parser import CobolParser
from cobol_wrap.ast import CobolProgram

def create_mock_cbl(td, content: str) -> str:
    path = os.path.join(td, "mock.cbl")
    with open(path, "w") as f:
        f.write(content)
    return path

def test_graphql_emission():
    with TemporaryDirectory() as td:
        cbl = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MOCKSERV.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
          01 WS-REQ PIC X(10).
       PROCEDURE DIVISION USING WS-REQ.
       MOCK-PARA.
           DISPLAY WS-REQ.
        """
        path = create_mock_cbl(td, cbl)
        out_dir = os.path.join(td, "api")
        wrap(path, output_dir=out_dir, graphql=True)
        
        gql_path = os.path.join(out_dir, "routes", "graphql_api.py")
        assert os.path.exists(gql_path)
        with open(gql_path, "r") as f:
            code = f.read()
            assert "import strawberry" in code
            assert "class Query:" in code
            assert "class Mutation:" in code
            # PROGRAM-ID is MOCKSERV, so entry point and mutation name is 'mockserv'
            assert "def mockserv(self" in code
            
def test_kafka_streaming_emission():
    with TemporaryDirectory() as td:
        cbl = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MOCKSERV.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       PROCEDURE DIVISION.
       FIRST-PARA.
           DISPLAY "ONE".
        """
        path = create_mock_cbl(td, cbl)
        out_dir = os.path.join(td, "api")
        wrap(path, output_dir=out_dir, kafka=True)
        
        kafka_path = os.path.join(out_dir, "routes", "kafka_consumers.py")
        assert os.path.exists(kafka_path)
        with open(kafka_path, "r") as f:
            code = f.read()
            assert "from faststream" in code
            assert "KafkaBroker" in code
            # PROGRAM-ID is MOCKSERV; topics derive from program_id, not filename
            assert "@broker.subscriber('cobol.mockserv.mockserv.in')" in code
            assert "@broker.publisher('cobol.mockserv.mockserv.out')" in code

def test_opentelemetry_injection():
    with TemporaryDirectory() as td:
        cbl = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MOCKSERV.
       PROCEDURE DIVISION.
       MOCK-PARA.
           DISPLAY "ONE".
        """
        path = create_mock_cbl(td, cbl)
        out_dir = os.path.join(td, "api")
        wrap(path, output_dir=out_dir, telemetry=True)
        
        server_path = os.path.join(out_dir, "server.py")
        proc_path = os.path.join(out_dir, "routes", "procedure.py")
        
        with open(server_path, "r") as f:
            server_code = f.read()
            assert "OTLPSpanExporter" in server_code
            assert "FastAPIInstrumentor.instrument_app(app)" in server_code
            
        with open(proc_path, "r") as f:
            proc_code = f.read()
            # PROGRAM-ID is MOCKSERV, so span name uses 'mockserv' not filename 'mock'
            assert "tracer.start_as_current_span('cobol_execute_mockserv'):" in proc_code

def test_semantic_aliasing():
    with TemporaryDirectory() as td:
        cbl = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MOCKSERV.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
       DATA DIVISION.
       FILE SECTION.
       FD CUST-MST-REC.
       01 CUSTOMER-RECORD.
          05 CUST-ID PIC X(10).
       WORKING-STORAGE SECTION.
       PROCEDURE DIVISION.
       MOCK-PARA.
           DISPLAY "ONE".
        """
        path = create_mock_cbl(td, cbl)
        out_dir = os.path.join(td, "api")
        # Generate with semantic mapping on
        wrap(path, output_dir=out_dir, semantic=True)
        
        models_path = os.path.join(out_dir, "models.py")
        with open(models_path, "r") as f:
            code = f.read()
            # fd.record_name = "CUSTOMER-RECORD" (actual 01-level name, not synthetic)
            # _beautify("CUSTOMER-RECORD", True) with semantic=True -> "CustomerRecord"
            assert "class CustomerRecord(BaseModel):" in code
            # _beautify("CUST-ID", False) with semantic=True: "CUST"->"customer", "ID"->"id" -> "customer_id"
            assert "customer_id:" in code
