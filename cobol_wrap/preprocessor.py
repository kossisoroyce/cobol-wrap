import re
import os
from tempfile import NamedTemporaryFile

class CobolPreprocessor:
    """
    Stage 0: Pre-compiler.
    - Resolves COPY statements.
    - Intercepts EXEC SQL and EXEC CICS, translating them to native CALL wrappers.
    """
    def __init__(self, copybook_dirs=None):
        self.copybook_dirs = copybook_dirs or []
        self.sql_operations = []
        self.cics_operations = []

    def process(self, cobol_path: str) -> str:
        with open(cobol_path, 'r') as f:
            lines = f.readlines()

        processed_lines = []
        in_sql = False
        in_cics = False
        sql_buffer = []
        cics_buffer = []

        for line in lines:
            line_upper = line.strip().upper()

            # --- COPY RESOLUTION ---
            if line_upper.startswith("COPY "):
                copy_match = re.search(r'COPY\s+([A-Z0-9\-]+)', line_upper)
                if copy_match:
                    copy_name = copy_match.group(1)
                    inlined = self._resolve_copybook(copy_name)
                    processed_lines.extend(inlined)
                continue

            # --- EXEC SQL TRANSLATOR ---
            if "EXEC SQL" in line_upper and not in_sql:
                sql_buffer = [line]
                if "END-EXEC" in line_upper:
                    call_id = len(self.sql_operations)
                    self._parse_sql_buffer(sql_buffer)
                    processed_lines.append(f"           CALL 'SQL-BRIDGE'.\n")
                else:
                    in_sql = True
                continue
                
            if in_sql:
                if "END-EXEC" in line_upper:
                    in_sql = False
                    sql_buffer.append(line)
                    call_id = len(self.sql_operations)
                    self._parse_sql_buffer(sql_buffer)
                    processed_lines.append(f"           CALL 'SQL-BRIDGE'.\n")
                else:
                    sql_buffer.append(line)
                continue

            # --- EXEC CICS TRANSLATOR ---
            if "EXEC CICS" in line_upper and not in_cics:
                cics_buffer = [line]
                if "END-EXEC" in line_upper:
                    call_id = len(self.cics_operations)
                    self._parse_cics_buffer(cics_buffer)
                    processed_lines.append(f"           CALL 'CICS-BRIDGE'.\n")
                else:
                    in_cics = True
                continue
                
            if in_cics:
                if "END-EXEC" in line_upper:
                    in_cics = False
                    cics_buffer.append(line)
                    call_id = len(self.cics_operations)
                    self._parse_cics_buffer(cics_buffer)
                    processed_lines.append(f"           CALL 'CICS-BRIDGE'.\n")
                else:
                    cics_buffer.append(line)
                continue

            processed_lines.append(line)

        # Write to temporary file for the parser to consume
        tmp = NamedTemporaryFile(delete=False, suffix=".cbl", mode='w')
        try:
            tmp.writelines(processed_lines)
        finally:
            tmp.close()
        return tmp.name
        
    def _resolve_copybook(self, name: str) -> list:
        """ Searches copybook dirs for <name>.cpy, <name>.cbl, or just <name> """
        extensions = [".cpy", ".cbl", ""]
        for d in self.copybook_dirs:
            for ext in extensions:
                p = os.path.join(d, name + ext)
                if os.path.exists(p):
                    with open(p, 'r') as f:
                        return f.readlines()
        
        # If not found, return a comment indicating unresolved
        return [f"      * UNRESOLVED COPY: {name}\n"]

    def _parse_sql_buffer(self, buffer: list):
        # Extract the SELECT/INSERT and the host variables :VAR
        query = " ".join([l.strip() for l in buffer])
        host_vars = re.findall(r':([A-Z0-9\-]+)', query)
        self.sql_operations.append({"query": query, "host_vars": host_vars})

    def _parse_cics_buffer(self, buffer: list):
        # Extract CICS commands like RECEIVE MAP, SEND MAP, RETURN
        cmd = " ".join([l.strip() for l in buffer])
        self.cics_operations.append({"command": cmd})
