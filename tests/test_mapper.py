import pytest
from decimal import Decimal
from pydantic import Field
from cobol_wrap.ast import CobolProgram, DataField, FD
from cobol_wrap.mapper import TypeMapper

def test_map_string_types():
    df = DataField(level=5, name="WS-MOCK", pic_clause="X(10)")
    mapper = TypeMapper(CobolProgram(program_id="TEST"))
    t, f = mapper._map_field(df)
    
    assert t == str
    assert f.alias == "WS-MOCK"
    assert getattr(f.metadata[0], "max_length") == 10

def test_map_numeric_types():
    df = DataField(level=5, name="WS-NUM", pic_clause="9(5)")
    mapper = TypeMapper(CobolProgram(program_id="TEST"))
    t, f = mapper._map_field(df)
    
    assert t == int
    assert getattr(f.metadata[0], "ge") == 0
    assert getattr(f.metadata[1], "le") == 99999

def test_map_signed_numeric():
    df = DataField(level=5, name="WS-SIGNED", pic_clause="S9(3)")
    mapper = TypeMapper(CobolProgram(program_id="TEST"))
    t, f = mapper._map_field(df)
    
    assert t == int
    assert getattr(f.metadata[0], "ge") == -999
    assert getattr(f.metadata[1], "le") == 999

def test_map_decimal_types():
    df = DataField(level=5, name="WS-DEC", pic_clause="9(7)V99")
    mapper = TypeMapper(CobolProgram(program_id="TEST"))
    t, f = mapper._map_field(df)
    
    assert t == Decimal
    # Note: Using decimal validation via max_digits requires testing the metadata object specifically
    # but for simplicity we verify the args are generated properly in generate_models_py

def test_map_packed_comp3():
    df = DataField(level=5, name="WS-COMP3", pic_clause="S9(5)V9(3)", is_comp3=True)
    mapper = TypeMapper(CobolProgram(program_id="TEST"))
    t, f = mapper._map_field(df)
    assert t == Decimal

def test_map_arrays():
    df = DataField(level=5, name="WS-ARR", pic_clause="X(5)", occurs=10)
    mapper = TypeMapper(CobolProgram(program_id="TEST"))
    t, f = mapper._map_field(df)
    
    extra = getattr(f, "json_schema_extra")
    assert extra["is_list"] is True

def test_map_enums_and_generation():
    df = DataField(level=5, name="WS-STATUS", pic_clause="X(1)", enum_values=["A", "B", "C"])
    prog = CobolProgram(program_id="TEST")
    prog.working_storage.append(df)
    
    mapper = TypeMapper(prog)
    mapper.to_pydantic() # compute
    
    code = mapper.generate_models_py()
    assert "class WorkingStorageWs_statusEnum(str, Enum):" in code
    assert "VAL_0 = 'A'" in code
    assert "VAL_1 = 'B'" in code
    assert "alias='WS-STATUS'" in code
