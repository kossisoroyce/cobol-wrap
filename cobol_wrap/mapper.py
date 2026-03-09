import re
from typing import Dict, Any, Type
from pydantic import create_model, Field, BaseModel
from decimal import Decimal
from .ast import CobolProgram, DataField


def _parse_v_decimal(pic: str):
    """
    Parse a COBOL PIC clause and return (int_digits, dec_places) for fixed-point types.
    Handles both V9(n) (parenthesized) and V99 (literal nines) notations.
    Returns None if no decimal part is found.
    """
    # Match V9(n) parenthesized form first, then fall back to literal nines
    v_match = re.search(r'S?9\((\d+)\)V(?:9\((\d+)\)|(9+))', pic)
    if v_match:
        int_digits = int(v_match.group(1))
        if v_match.group(2):
            dec_places = int(v_match.group(2))
        else:
            dec_places = len(v_match.group(3))
        return int_digits, dec_places
    return None


class TypeMapper:
    """
    Maps COBOL data types (PIC clauses) to Python/Pydantic models.
    """
    def __init__(self, program: CobolProgram, semantic: bool = False):
        self.program = program
        self.semantic = semantic
        self.models: Dict[str, Type[BaseModel]] = {}

    def _beautify(self, text: str, is_class: bool = False) -> str:
        if not self.semantic:
            return ''.join(w.capitalize() for w in text.split('-')) if is_class else text.replace('-', '_').lower()

        # NLP hook simulation: translate CUST-MST-REC -> CustomerMasterRecord
        words = text.split('-')
        expansions = {
            "CUST": "Customer", "MST": "Master", "REC": "Record",
            "WS": "WorkingStorage", "STR": "String", "NUM": "Number",
            "DEC": "Decimal", "ARR": "Array"
        }
        expanded = [expansions.get(w, w.capitalize() if is_class else w.lower()) for w in words]

        if is_class:
            return "".join([w.capitalize() for w in expanded])
        return "_".join([w.lower() for w in expanded])

    def to_pydantic(self) -> Dict[str, Type[BaseModel]]:
        """
        Creates Pydantic models for the data structures in the COBOL program.
        """
        # FD record models: use each root record's children as fields
        for fd in self.program.file_descriptions:
            model_name = self._beautify(fd.record_name, True)
            # If root record has children, use them as the model fields (actual data items)
            root = fd.fields[0] if fd.fields else None
            if root and root.children:
                flat_fields = root.children
            else:
                flat_fields = fd.fields
            fields = {self._beautify(f.name, False): self._map_field(f) for f in flat_fields}
            self.models[model_name] = create_model(model_name, **fields)

        # Working-storage: create one model per 01-level group (using its children)
        for root_field in self.program.working_storage:
            if root_field.children:
                child_fields = {
                    self._beautify(f.name, False): self._map_field(f)
                    for f in root_field.children
                }
                model_name = self._beautify(root_field.name, True)
                self.models[model_name] = create_model(model_name, **child_fields)

        # Flat WS items (level > 1 added directly, or level-77 standalone fields)
        ws_flat = {
            self._beautify(f.name, False): self._map_field(f)
            for f in self.program.working_storage
            if not f.children and f.pic_clause
        }
        if ws_flat:
            self.models["WorkingStorage"] = create_model("WorkingStorage", **ws_flat)

        # Request/response models for each procedure entry point
        for ep in self.program.procedure_division:
            req_name = f"{ep.name.replace('-', '').capitalize()}Request"
            res_name = f"{ep.name.replace('-', '').capitalize()}Response"

            req_fields = {}
            for param in ep.params:
                matched_field = next(
                    (f for f in self.program.linkage_section if f.name.upper() == param.upper()),
                    None
                )
                if matched_field:
                    req_fields[self._beautify(param, False)] = self._map_field(matched_field)

            if req_fields:
                self.models[req_name] = create_model(req_name, **req_fields)
                self.models[res_name] = create_model(res_name, **req_fields)
            else:
                self.models[req_name] = create_model(req_name, payload=(Dict[str, Any], ...))
                self.models[res_name] = create_model(res_name, payload=(Dict[str, Any], ...))

        return self.models

    def _map_field(self, field: DataField) -> tuple:
        """
        Returns a tuple of (type, Field(...)) for Pydantic.
        """
        alias = field.name
        base_type = str
        field_kwargs = {"alias": alias}

        if field.enum_values:
            base_type = str
            field_kwargs["json_schema_extra"] = {"is_enum": True, "enum_values": field.enum_values}
        elif getattr(field, "is_pointer", False):
            base_type = Any
            field_kwargs["json_schema_extra"] = {"is_pointer": True}
        elif getattr(field, "is_national", False):
            base_type = str
            field_kwargs["json_schema_extra"] = {"is_national": True}
        elif field.pic_clause:
            pic = field.pic_clause.upper().replace(" ", "")

            # Fixed-point decimal: PIC 9(n)V99 or PIC 9(n)V9(m) or COMP-3
            dec_result = _parse_v_decimal(pic)
            if dec_result or field.is_comp3:
                if dec_result:
                    int_digits, dec_places = dec_result
                    d_digits = int_digits + dec_places
                    d_places = dec_places
                else:
                    d_digits, d_places = 18, 4
                base_type = Decimal
                field_kwargs.update({"max_digits": d_digits, "decimal_places": d_places})

            # PIC S9(n) — signed integer
            elif 'S' in pic and '9' in pic:
                int_match = re.search(r'9\((\d+)\)', pic)
                digits = int(int_match.group(1)) if int_match else 4
                base_type = int
                field_kwargs.update({"ge": -(10 ** digits - 1), "le": 10 ** digits - 1})

            # PIC 9(n) or COMP/BINARY — unsigned integer
            elif '9' in pic or field.is_comp:
                int_match = re.search(r'9\((\d+)\)', pic)
                digits = int(int_match.group(1)) if int_match else 4
                base_type = int
                field_kwargs.update({"ge": 0, "le": 10 ** digits - 1})

            # PIC X(n) or A(n) — string
            else:
                str_match = re.search(r'[XA]\((\d+)\)', pic)
                if str_match:
                    length = int(str_match.group(1))
                    base_type = str
                    field_kwargs.update({"max_length": length})

        # Array (OCCURS) annotation
        if field.occurs or field.occurs_depending_on:
            field_kwargs["json_schema_extra"] = field_kwargs.get("json_schema_extra", {})
            field_kwargs["json_schema_extra"]["is_list"] = True
            if field.occurs:
                field_kwargs.update({"min_length": field.occurs, "max_length": field.occurs})

        # REDEFINES annotation
        if field.redefines:
            field_kwargs["json_schema_extra"] = field_kwargs.get("json_schema_extra", {})
            field_kwargs["json_schema_extra"]["is_redefines"] = True
            field_kwargs["json_schema_extra"]["redefines_target"] = field.redefines

        return (base_type, Field(**field_kwargs))

    def generate_models_py(self) -> str:
        """
        Generates the literal source code for models.py
        """
        lines = [
            "# Auto-generated by cobol-wrap",
            "from pydantic import BaseModel, ConfigDict, Field",
            "from decimal import Decimal",
            "from enum import Enum",
            "from typing import Optional, List, Union, Dict, Any\n"
        ]

        # Generate inline Enums
        for name, model in self.models.items():
            for field_name, model_field in model.model_fields.items():
                extra = model_field.json_schema_extra or {}
                if extra.get("is_enum"):
                    enum_name = f"{name}{field_name.capitalize()}Enum"
                    lines.append(f"class {enum_name}(str, Enum):")
                    for idx, val in enumerate(extra.get("enum_values")):
                        lines.append(f"    VAL_{idx} = '{val}'")
                    lines.append("")

        for name, model in self.models.items():
            lines.append(f"class {name}(BaseModel):")
            lines.append(f"    model_config = ConfigDict(populate_by_name=True)")
            lines.append("")
            for field_name, model_field in model.model_fields.items():

                extra = model_field.json_schema_extra or {}
                ann = model_field.annotation.__name__ if hasattr(model_field.annotation, '__name__') else str(model_field.annotation)

                if extra.get("is_enum"):
                    ann = f"{name}{field_name.capitalize()}Enum"

                if extra.get("is_list"):
                    ann = f"List[{ann}]"

                if extra.get("is_redefines"):
                    ann = f"Optional[{ann}]"

                # Build Field(...) string preserving all properties
                fargs = []
                if model_field.alias:
                    fargs.append(f"alias='{model_field.alias}'")

                if hasattr(model_field, "metadata"):
                    for m in model_field.metadata:
                        if hasattr(m, "max_digits"):
                            fargs.append(f"max_digits={m.max_digits}")
                            fargs.append(f"decimal_places={m.decimal_places}")
                        if hasattr(m, "ge"):
                            fargs.append(f"ge={m.ge}")
                        if hasattr(m, "le"):
                            fargs.append(f"le={m.le}")
                        if hasattr(m, "max_length"):
                            fargs.append(f"max_length={m.max_length}")
                        if hasattr(m, "min_length"):
                            fargs.append(f"min_length={m.min_length}")

                if extra.get("is_redefines"):
                    field_str = "Field(default=None, " + ", ".join(fargs) + ")" if fargs else "Field(default=None)"
                else:
                    field_str = "Field(..., " + ", ".join(fargs) + ")" if fargs else "Field(...)"

                lines.append(f"    {field_name}: {ann} = {field_str}")

            if not model.model_fields:
                lines.append("    pass")
            lines.append("\n")

        return "\n".join(lines)
