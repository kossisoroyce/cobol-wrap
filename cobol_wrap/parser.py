import logging
import os
import re
from pathlib import Path

from .ast import FD, CobolProgram, DataField, EntryPoint

logger = logging.getLogger(__name__)

COBOL_MARKERS = {"IDENTIFICATION DIVISION", "PROGRAM-ID", "DATA DIVISION",
                 "PROCEDURE DIVISION", "WORKING-STORAGE", "LINKAGE SECTION"}


class CobolParser:
    """
    Primary Regex-based AST Syntax Engine.
    Parses COBOL source code and handles advanced edge cases like REDEFINES, OCCURS, and Nested Hierarchies.
    """
    def __init__(self, parser_jar_path: str = None):
        # parser_jar_path argument maintained for legacy backwards compatibility
        pass

    def parse(self, program_path: str) -> CobolProgram:
        """
        Parses a .cbl file and returns the structured CobolProgram AST.
        """
        if not os.path.exists(program_path):
            raise FileNotFoundError(
                f"COBOL source file not found: {program_path}\n\n"
                f"  If you're using copybooks, make sure to pass --copybook-dir.\n"
                f"  Example: cobol-wrap load program.cbl --copybook-dir ./copybooks/"
            )

        program_id = Path(program_path).stem
        program = CobolProgram(program_id=program_id)

        with open(program_path, 'r') as f:
            content = f.read()

        # Validate that this looks like COBOL source (check for division markers
        # or at least PIC/level-number data definitions)
        content_upper = content.upper()
        has_markers = any(marker in content_upper for marker in COBOL_MARKERS)
        has_data_items = bool(re.search(r'^\s*\d{2}\s+[A-Z]', content_upper, re.MULTILINE))
        if not has_markers and not has_data_items:
            raise ValueError(
                f"The file '{program_path}' does not appear to contain valid COBOL source code.\n\n"
                f"  No IDENTIFICATION DIVISION, PROGRAM-ID, PROCEDURE DIVISION, or data definitions found.\n"
                f"  Make sure you're pointing to a .cbl or .cob COBOL source file."
            )

        lines = content.splitlines()
        current_fd = None
        last_field = None
        current_section = "WORKING-STORAGE"

        # Stack to track hierarchy natively
        stack = []

        # Pending FILE-CONTROL attributes (keyed by SELECT file-name) applied when FD is declared
        pending_file_attrs: dict = {}  # {fd_name_upper: {is_indexed, record_key}}
        current_select_name = None

        for line in lines:
            line = line.strip().upper()
            if not line or line.startswith("*"):
                continue

            # --- PROGRAM-ID extraction (overrides filename-based default) ---
            prog_id_match = re.search(r'PROGRAM-ID[.\s]+([A-Z0-9\-]+)', line)
            if prog_id_match:
                program.program_id = prog_id_match.group(1).strip('.')
                continue

            # --- Section transitions ---
            if "FILE SECTION" in line:
                current_section = "FILE"
                stack = []
                continue

            if "WORKING-STORAGE SECTION" in line:
                current_section = "WORKING-STORAGE"
                current_fd = None  # Bug fix: clear FD context when leaving FILE SECTION
                stack = []
                continue

            if "LINKAGE SECTION" in line:
                current_section = "LINKAGE"
                current_fd = None  # Bug fix: clear FD context
                stack = []
                continue

            # --- FILE-CONTROL SELECT statement (maps logical name to FD) ---
            select_match = re.search(r'SELECT\s+([A-Z0-9\-]+)', line)
            if select_match:
                current_select_name = select_match.group(1)
                if current_select_name not in pending_file_attrs:
                    pending_file_attrs[current_select_name] = {}

            # --- VSAM attributes in FILE-CONTROL (before FD is declared) ---
            idx_match = re.search(r'ORGANIZATION\s+IS\s+INDEXED', line)
            if idx_match:
                if current_fd:
                    current_fd.is_indexed = True
                elif current_select_name:
                    pending_file_attrs[current_select_name]["is_indexed"] = True

            key_match = re.search(r'RECORD\s+KEY\s+IS\s+([A-Z0-9\-]+)', line)
            if key_match:
                if current_fd:
                    current_fd.record_key = key_match.group(1)
                elif current_select_name:
                    pending_file_attrs[current_select_name]["record_key"] = key_match.group(1)

            # --- FD entry ---
            if line.startswith("FD "):
                fd_name = line.split()[1].strip(".")
                current_fd = FD(name=fd_name, record_name=f"{fd_name}-REC")
                # Apply any pending FILE-CONTROL attributes for this FD
                attrs = pending_file_attrs.get(fd_name, {})
                if attrs.get("is_indexed"):
                    current_fd.is_indexed = True
                if attrs.get("record_key"):
                    current_fd.record_key = attrs["record_key"]
                program.file_descriptions.append(current_fd)
                stack = []  # Reset hierarchy for new FD
                continue

            # --- DEPENDING ON continuation line (when OCCURS spans multiple lines) ---
            dep_only = re.search(r'^DEPENDING\s+ON\s+([A-Z0-9\-]+)', line)
            if dep_only and last_field and not re.search(r'^(\d{2})\s+', line):
                last_field.occurs_depending_on = dep_only.group(1)
                continue

            # --- 88-level (enum values) ---
            enum_match = re.search(r'88\s+([A-Z0-9\-]+)\s+VALUE\s+[\'"]?([^\'".\s][^\'".]*)[\'"]?', line)
            if enum_match and last_field:
                last_field.enum_values.append(enum_match.group(2).strip())
                continue

            # --- Data field (level + name) ---
            pic_match = re.search(r'^(\d{2})\s+([A-Z0-9\-]+)', line)
            if pic_match:
                level = int(pic_match.group(1))
                name = pic_match.group(2)

                df = DataField(level=level, name=name)

                pic_clause = re.search(r'PIC\s+([A-Z0-9\(\)VS]+)', line)
                if pic_clause:
                    df.pic_clause = pic_clause.group(1)

                redefines = re.search(r'REDEFINES\s+([A-Z0-9\-]+)', line)
                if redefines:
                    df.redefines = redefines.group(1)

                # Range OCCURS: OCCURS min TO max TIMES [DEPENDING ON var]
                occurs_range = re.search(r'OCCURS\s+\d+\s+TO\s+(\d+)\s+TIMES', line)
                if occurs_range:
                    df.occurs = int(occurs_range.group(1))  # use maximum size

                # Simple OCCURS (only if range not already matched)
                elif re.search(r'OCCURS\s+(\d+)\s+TIMES', line):
                    occurs_simple = re.search(r'OCCURS\s+(\d+)\s+TIMES', line)
                    df.occurs = int(occurs_simple.group(1))

                # OCCURS DEPENDING ON — matches both bare and range forms:
                #   OCCURS DEPENDING ON VAR
                #   OCCURS 1 TO 10 TIMES DEPENDING ON VAR
                occurs_dep = re.search(r'DEPENDING\s+ON\s+([A-Z0-9\-]+)', line)
                if occurs_dep:
                    df.occurs_depending_on = occurs_dep.group(1)

                if 'COMP-3' in line or 'PACKED-DECIMAL' in line:
                    df.is_comp3 = True
                elif 'COMP ' in line or 'COMP.' in line or 'BINARY' in line:
                    df.is_comp = True

                if 'USAGE POINTER' in line:
                    df.is_pointer = True
                if 'NATIONAL' in line or (df.pic_clause and 'N' in df.pic_clause):
                    df.is_national = True

                # --- Hierarchy resolution ---
                while stack and stack[-1].level >= level:
                    stack.pop()

                if stack:
                    stack[-1].children.append(df)
                else:
                    if current_fd:
                        # Update fd.record_name with the actual 01-level record name
                        if not current_fd.fields:  # first field into this FD
                            current_fd.record_name = name
                        current_fd.fields.append(df)
                    elif current_section == "LINKAGE":
                        program.linkage_section.append(df)
                    else:
                        program.working_storage.append(df)

                stack.append(df)
                last_field = df

            # --- PROCEDURE DIVISION entry point ---
            if "PROCEDURE DIVISION" in line:
                params_match = re.search(r'USING\s+(.+?)\.?\s*$', line)
                params = params_match.group(1).split() if params_match else []
                ep = EntryPoint(name=program.program_id, params=params)
                program.procedure_division.append(ep)

        return program
