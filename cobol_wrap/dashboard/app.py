from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import os
import shutil
import json
from pathlib import Path

app = FastAPI(title="cobol-wrap Local Dashboard", description="Visual UI for interacting with locally compiled COBOL binaries.")

MODELS_DIR = os.path.expanduser("~/.cobol-wrap/models")

def get_models_list():
    if not os.path.exists(MODELS_DIR):
        return []
    models = []
    for d in os.listdir(MODELS_DIR):
        model_path = os.path.join(MODELS_DIR, d)
        if os.path.isdir(model_path):
            size = sum(f.stat().st_size for f in Path(model_path).rglob('*') if f.is_file())
            mtime = os.path.getmtime(model_path)

            # Extract endpoints from openapi.yaml
            openapi_path = os.path.join(model_path, "openapi.yaml")
            endpoints = []
            if os.path.exists(openapi_path):
                import yaml
                with open(openapi_path, 'r') as f:
                    spec = yaml.safe_load(f)
                    if spec and 'paths' in spec:
                        endpoints = list(spec['paths'].keys())

            models.append({
                "name": d,
                "size_kb": round(size / 1024, 1),
                "modified": mtime,
                "endpoints": endpoints
            })
    return sorted(models, key=lambda x: x["modified"], reverse=True)


@app.get("/api/models")
async def list_models():
    """Returns the JSON list of models to populate the dashboard."""
    return {"models": get_models_list()}


@app.get("/api/models/{name}/spec")
async def get_model_spec(name: str):
    """Returns the OpenAPI spec for a given model as JSON."""
    model_path = os.path.join(MODELS_DIR, name)
    if not os.path.isdir(model_path):
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found.")

    openapi_path = os.path.join(model_path, "openapi.yaml")
    if not os.path.exists(openapi_path):
        raise HTTPException(status_code=404, detail=f"OpenAPI spec not found for model '{name}'.")

    import yaml
    with open(openapi_path, 'r') as f:
        spec = yaml.safe_load(f)
    return spec or {}


@app.delete("/api/models/{name}")
async def delete_model(name: str):
    """Removes a model from the local registry."""
    model_path = os.path.join(MODELS_DIR, name)
    if not os.path.isdir(model_path):
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found.")
    shutil.rmtree(model_path)
    return {"status": "deleted", "name": name}


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serves the Vanilla JS HTML single page application."""
    ui_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(ui_path, "r") as f:
        return f.read()
