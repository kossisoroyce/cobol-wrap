from typing import List, Optional

from pydantic import BaseModel, Field


class DataField(BaseModel):
    level: int
    name: str
    pic_clause: Optional[str] = None
    occurs: Optional[int] = None
    occurs_depending_on: Optional[str] = None
    redefines: Optional[str] = None
    value: Optional[str] = None
    is_comp: bool = False
    is_comp3: bool = False
    is_pointer: bool = False
    is_national: bool = False
    enum_values: List[str] = Field(default_factory=list)
    children: List['DataField'] = Field(default_factory=list)

class EntryPoint(BaseModel):
    name: str
    params: List[str] = Field(default_factory=list)

class FD(BaseModel):
    name: str
    record_name: str
    is_indexed: bool = False
    record_key: Optional[str] = None
    fields: List[DataField] = Field(default_factory=list)

class CobolProgram(BaseModel):
    program_id: str
    data_division: List[DataField] = Field(default_factory=list)
    working_storage: List[DataField] = Field(default_factory=list)
    linkage_section: List[DataField] = Field(default_factory=list)
    procedure_division: List[EntryPoint] = Field(default_factory=list)
    file_descriptions: List[FD] = Field(default_factory=list)

# Need this for recursive DataField resolution
DataField.model_rebuild()
