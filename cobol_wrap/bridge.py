import os
import re
from .ast import CobolProgram


def _sanitize_identifier(name: str) -> str:
    """Strip anything outside [a-zA-Z0-9_] to prevent injection in generated SQL/Python."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


class FlatFileBridgeEmitter:
    """Generates flat file CRUD endpoints wrapper based on FD definitions."""

    def __init__(self, program: CobolProgram):
        self.program = program

    def emit(self, output_dir: str):
        if not self.program.file_descriptions:
            return

        routes_dir = os.path.join(output_dir, "routes")
        os.makedirs(routes_dir, exist_ok=True)

        lines = [
            "from fastapi import APIRouter, HTTPException",
            "from typing import List, Dict, Any",
            "import os",
            "import sqlite3",
            "import json",
            "from models import *",
            "",
            "router = APIRouter()",
            "",
            "def get_db(db_name):",
            "    db_path = os.path.join(os.path.dirname(__file__), '..', f'{db_name}.db')",
            "    conn = sqlite3.connect(db_path)",
            "    conn.row_factory = sqlite3.Row",
            "    return conn",
            ""
        ]

        for fd in self.program.file_descriptions:
            route = fd.name.lower()
            route_id = _sanitize_identifier(route)
            model = ''.join(w.capitalize() for w in fd.record_name.split('-'))
            key_col = _sanitize_identifier(
                fd.record_key.lower().replace('-', '_')
            ) if getattr(fd, 'is_indexed', False) and getattr(fd, 'record_key', None) else "id"
            key_col_sql = key_col.upper()

            lines.append(f"")
            if getattr(fd, 'is_indexed', False):
                lines.append(f"# --- VSAM INDEXED KSDS SQLite Adapter for {fd.name} ---")
                lines.append(f"def init_{route_id}_table():")
                lines.append(f"    with get_db('{route}') as db:")
                lines.append(f"        db.execute('CREATE TABLE IF NOT EXISTS records ({key_col_sql} TEXT PRIMARY KEY, data JSON)')")
                lines.append(f"init_{route_id}_table()")
            else:
                lines.append(f"# --- SEQUENTIAL Object Adapter for {fd.name} ---")

            # CREATE
            lines.append(f"@router.post('/{route}')")
            lines.append(f"def create_{route_id}(record: {model}):")
            if getattr(fd, 'is_indexed', False):
                lines.append(f"    with get_db('{route}') as db:")
                lines.append(f"        try:")
                lines.append(f"            db.execute('INSERT INTO records ({key_col_sql}, data) VALUES (?, ?)', (getattr(record, '{key_col}', None) or __import__('uuid').uuid4().hex, record.model_dump_json()))")
                lines.append(f"            db.commit()")
                lines.append(f"        except sqlite3.IntegrityError:")
                lines.append(f"            raise HTTPException(status_code=400, detail='Record with this key already exists. Use a unique key value or update the existing record.')")
                lines.append(f"    return {{'status': 'success'}}")
            else:
                lines.append(f"    with open(os.path.join(os.path.dirname(__file__), '..', '{fd.name}.dat'), 'a') as f:")
                lines.append(f"        f.write( record.model_dump_json() + '\\n' )")
                lines.append(f"    return {{'status': 'success'}}")

            # READ
            lines.append(f"")
            lines.append(f"@router.get('/{route}')")
            lines.append(f"def read_{route_id}(id: str = None):")
            if getattr(fd, 'is_indexed', False):
                 lines.append(f"    with get_db('{route}') as db:")
                 lines.append(f"        if id:")
                 lines.append(f"            row = db.execute('SELECT data FROM records WHERE {key_col_sql} = ?', (id,)).fetchone()")
                 lines.append(f"            if not row: raise HTTPException(status_code=404, detail=f'No record found with key \"{{id}}\". Use GET /{route} to list all records.')")
                 lines.append(f"            return json.loads(row['data'])")
                 lines.append(f"        rows = db.execute('SELECT data FROM records').fetchall()")
                 lines.append(f"        return [json.loads(r['data']) for r in rows]")
            else:
                dat_path = f"os.path.join(os.path.dirname(__file__), '..', '{fd.name}.dat')"
                lines.append(f"    _dat = {dat_path}")
                lines.append(f"    if not os.path.exists(_dat): return []")
                lines.append(f"    with open(_dat, 'r') as f:")
                lines.append(f"        return [json.loads(line.strip()) for line in f if line.strip()]")

            # UPDATE and DELETE — VSAM indexed files only
            if getattr(fd, 'is_indexed', False):
                # UPDATE (REWRITE)
                lines.append(f"")
                lines.append(f"@router.put('/{route}/{{record_id}}')")
                lines.append(f"def update_{route_id}(record_id: str, record: {model}):")
                lines.append(f"    with get_db('{route}') as db:")
                lines.append(f"        existing = db.execute('SELECT 1 FROM records WHERE {key_col_sql} = ?', (record_id,)).fetchone()")
                lines.append(f"        if not existing:")
                lines.append(f"            raise HTTPException(status_code=404, detail=f'No record found with key \"{{record_id}}\". Cannot update a record that does not exist.')")
                lines.append(f"        db.execute('UPDATE records SET data = ? WHERE {key_col_sql} = ?', (record.model_dump_json(), record_id))")
                lines.append(f"        db.commit()")
                lines.append(f"    return {{'status': 'updated'}}")

                # DELETE
                lines.append(f"")
                lines.append(f"@router.delete('/{route}/{{record_id}}')")
                lines.append(f"def delete_{route_id}(record_id: str):")
                lines.append(f"    with get_db('{route}') as db:")
                lines.append(f"        existing = db.execute('SELECT 1 FROM records WHERE {key_col_sql} = ?', (record_id,)).fetchone()")
                lines.append(f"        if not existing:")
                lines.append(f"            raise HTTPException(status_code=404, detail=f'No record found with key \"{{record_id}}\". Nothing to delete.')")
                lines.append(f"        db.execute('DELETE FROM records WHERE {key_col_sql} = ?', (record_id,))")
                lines.append(f"        db.commit()")
                lines.append(f"    return {{'status': 'deleted'}}")

        output_path = os.path.join(routes_dir, "flatfiles.py")
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
