import pytest
from cobol_wrap.parser import CobolParser
from cobol_wrap.ast import CobolProgram

def create_mock_cbl(tmp_path, content: str) -> str:
    p = tmp_path / "mock.cbl"
    p.write_text(content)
    return str(p)

def test_parse_standard_types(tmp_path):
    cbl = """
       01 WS-STANDARD-REC.
          05 WS-STR         PIC X(10).
          05 WS-ALPHA       PIC A(5).
          05 WS-NUM         PIC 9(4).
          05 WS-NUM-DEC     PIC 9(5)V99.
          05 WS-SIGNED      PIC S9(3).
    """
    path = create_mock_cbl(tmp_path, cbl)
    parser = CobolParser()
    prog = parser.parse(path)
    
    ws = prog.working_storage
    assert len(ws) == 1
    assert len(ws[0].children) == 5
    assert ws[0].children[0].name == "WS-STR"
    assert ws[0].children[0].pic_clause == "X(10)"
    assert ws[0].children[3].pic_clause == "9(5)V99"
    assert ws[0].children[4].pic_clause == "S9(3)"

def test_parse_computational_types(tmp_path):
    cbl = """
       01 WS-COMP-REC.
          05 WS-COMP3       PIC S9(7)V99 COMP-3.
          05 WS-COMP        PIC 9(4) COMP.
          05 WS-BIN         PIC 9(9) BINARY.
    """
    path = create_mock_cbl(tmp_path, cbl)
    parser = CobolParser()
    prog = parser.parse(path)
    
    ws = prog.working_storage
    assert len(ws) == 1
    assert ws[0].children[0].is_comp3 is True
    assert ws[0].children[1].is_comp is True
    assert ws[0].children[2].is_comp is True

def test_parse_redefines_and_occurs(tmp_path):
    cbl = """
       01 WS-ARRAY-REC.
          05 WS-ARRAY       PIC X(10) OCCURS 5 TIMES.
          05 WS-DYNAMIC     PIC X(1) OCCURS DEPENDING ON WS-COUNT.
          05 WS-RAW         PIC X(50).
          05 WS-MAP REDEFINES WS-RAW PIC 9(50).
    """
    path = create_mock_cbl(tmp_path, cbl)
    parser = CobolParser()
    prog = parser.parse(path)
    
    ws = prog.working_storage
    assert len(ws) == 1
    assert ws[0].children[0].occurs == 5
    assert ws[0].children[1].occurs_depending_on == "WS-COUNT"
    assert ws[0].children[3].redefines == "WS-RAW"

def test_parse_88_values(tmp_path):
    cbl = """
       01 WS-STATUS-REC.
          05 STATUS-CODE    PIC X(1).
             88 IS-ACTIVE   VALUE 'A'.
             88 IS-INACTIVE VALUE 'I'.
             88 IS-PENDING  VALUE "P".
    """
    path = create_mock_cbl(tmp_path, cbl)
    parser = CobolParser()
    prog = parser.parse(path)
    
    ws = prog.working_storage
    assert len(ws) == 1
    assert len(ws[0].children) == 1
    assert ws[0].children[0].name == "STATUS-CODE"
    assert ws[0].children[0].enum_values == ['A', 'I', 'P']

def test_parse_multiple_paragraphs(tmp_path):
    cbl = """
       PROCEDURE DIVISION USING PARAM-A.
       FIRST-PARA.
           DISPLAY "ONE".
       SECOND-PARA.
           DISPLAY "TWO".
    """
    path = create_mock_cbl(tmp_path, cbl)
    parser = CobolParser()
    prog = parser.parse(path)
    
    assert len(prog.procedure_division) == 1
    assert prog.procedure_division[0].params == ["PARAM-A"]
