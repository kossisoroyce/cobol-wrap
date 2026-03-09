"""
cobol-wrap CLI — Ollama-style local engine for COBOL APIs.

Load, serve, inspect, and manage COBOL programs as REST APIs
from your terminal. Designed to feel warm, helpful, and intuitive.
"""

import typer
import os
import sys
import shutil
import subprocess
import logging
import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from cobol_wrap import __version__, COBOL_EXTENSIONS

console = Console()
MODELS_DIR = os.path.expanduser("~/.cobol-wrap/models")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(message: str, hint: str = None, suggestion: str = None):
    """Print a formatted error block with optional hint and suggestion."""
    console.print()
    console.print(f"  [bold red]Error:[/bold red] {message}")
    if hint:
        console.print(f"  [dim]Hint:[/dim] {hint}")
    if suggestion:
        console.print(f"  [dim]Try:[/dim]  [cyan]{suggestion}[/cyan]")
    console.print()


def _success(message: str):
    """Print a formatted success message."""
    console.print(f"  [bold green]Done:[/bold green] {message}")


def _get_model_dir(name: str) -> str:
    return os.path.join(MODELS_DIR, name)


def _model_exists(name: str) -> bool:
    return os.path.isdir(_get_model_dir(name))


def _is_compiled(model_dir: str, name: str) -> bool:
    """Check if the native COBOL binary exists for a model."""
    rt = os.path.join(model_dir, "runtime")
    return any(
        os.path.exists(os.path.join(rt, f"{name}{ext}"))
        for ext in (".so", ".dylib")
    )


def _read_openapi_paths(model_dir: str) -> list:
    """Read endpoint paths from a model's openapi.yaml."""
    openapi_path = os.path.join(model_dir, "openapi.yaml")
    if not os.path.exists(openapi_path):
        return []
    try:
        import yaml
        with open(openapi_path, 'r') as f:
            spec = yaml.safe_load(f)
        return list((spec or {}).get("paths", {}).keys())
    except Exception:
        return []


def _read_openapi_spec(model_dir: str) -> dict:
    """Read the full OpenAPI spec as a dict."""
    openapi_path = os.path.join(model_dir, "openapi.yaml")
    if not os.path.exists(openapi_path):
        return {}
    import yaml
    with open(openapi_path, 'r') as f:
        return yaml.safe_load(f) or {}


def _dir_size_kb(path: str) -> float:
    """Total file size in KB for a directory."""
    total = sum(f.stat().st_size for f in Path(path).rglob('*') if f.is_file())
    return round(total / 1024, 1)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

def _version_callback(value: bool):
    if value:
        console.print(f"cobol-wrap [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


app = typer.Typer(
    help="cobol-wrap — The Ollama-style local engine for COBOL APIs.\n\n"
         "Parse COBOL source files, generate production REST APIs, and serve them locally.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v",
        help="Show the cobol-wrap version and exit.",
        callback=_version_callback, is_eager=True,
    ),
    verbose: bool = typer.Option(
        False, "--verbose",
        help="Enable detailed debug logging.",
    ),
):
    """cobol-wrap — The Ollama-style local engine for COBOL APIs."""
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

@app.command()
def load(
    program: str = typer.Argument(..., help="Path to the COBOL source file (.cbl, .cob)"),
    name: str = typer.Option(None, "--name", "-n", help="Model name (defaults to source filename)"),
    framework: str = typer.Option("fastapi", help="Output framework: fastapi | express"),
    docker: bool = typer.Option(True, "--docker/--no-docker", help="Include Docker deployment files"),
    flat_files: bool = typer.Option(False, "--flat-files", help="Generate flat file CRUD bridge endpoints"),
    vsam: bool = typer.Option(False, "--vsam", help="Generate VSAM-style indexed file bridge (SQLite-backed)"),
    copybook_dir: str = typer.Option(None, "--copybook-dir", "-c", help="Directory to search for COPY includes"),
    db_url: str = typer.Option(None, "--db-url", help="Database URL for intercepted EXEC SQL blocks"),
    mock_cics: bool = typer.Option(False, "--mock-cics", help="Intercept EXEC CICS to JSON payload hooks"),
    graphql: bool = typer.Option(False, "--graphql", help="Generate Strawberry GraphQL API layer"),
    kafka: bool = typer.Option(False, "--kafka", help="Generate FastStream Kafka consumer bindings"),
    telemetry: bool = typer.Option(False, "--telemetry", help="Inject OpenTelemetry distributed traces"),
    semantic: bool = typer.Option(False, "--semantic", help="Beautify COBOL field names with NLP expansion"),
):
    """Parse a COBOL source file and generate a complete REST API.

    This command preprocesses copybooks and EXEC blocks, parses the COBOL AST,
    maps PIC clauses to Pydantic types, and emits a FastAPI server with OpenAPI
    spec, ctypes shim, and optional Docker/GraphQL/Kafka/Telemetry layers.
    """
    model_name = name or Path(program).stem.lower()
    output_dir = _get_model_dir(model_name)

    # --- Input validation ---
    if not os.path.exists(program):
        _error(
            f"File not found: [bold]{program}[/bold]",
            hint="Make sure you're passing the full path to your COBOL source file.",
            suggestion=f"cobol-wrap load ./programs/{Path(program).name}",
        )
        raise typer.Exit(code=1)

    ext = Path(program).suffix
    if ext and ext not in COBOL_EXTENSIONS:
        console.print(f"  [yellow]Note:[/yellow] '{Path(program).name}' doesn't have a standard "
                       f"COBOL extension ({', '.join(sorted(COBOL_EXTENSIONS))}). Proceeding anyway.\n")

    if os.path.getsize(program) == 0:
        _error("The source file is empty.", hint="Check that the file has COBOL source code in it.")
        raise typer.Exit(code=1)

    # --- Begin loading ---
    console.print()
    console.print(f"  [bold cyan]Loading[/bold cyan] [bold]{Path(program).name}[/bold] "
                  f"as model [bold green]'{model_name}'[/bold green]...")
    console.print()

    if os.path.exists(output_dir):
        console.print(f"  [yellow]Replacing existing model '{model_name}'...[/yellow]")
        shutil.rmtree(output_dir)

    os.makedirs(MODELS_DIR, exist_ok=True)

    from cobol_wrap import wrap
    from cobol_wrap.preprocessor import CobolPreprocessor

    try:
        # Preprocess
        copy_dirs = [copybook_dir] if copybook_dir else []
        pre = CobolPreprocessor(copybook_dirs=copy_dirs)
        processed_path = pre.process(program)

        if pre.sql_operations:
            console.print(f"  [blue]Intercepted[/blue] {len(pre.sql_operations)} EXEC SQL block(s) "
                          f"— replaced with CALL 'SQL-BRIDGE' stubs.")
        if pre.cics_operations:
            console.print(f"  [blue]Intercepted[/blue] {len(pre.cics_operations)} EXEC CICS block(s) "
                          f"— replaced with CALL 'CICS-BRIDGE' stubs.")

        # Generate API
        def _on_progress(msg):
            console.print(f"  [dim]{msg}[/dim]")

        summary = wrap(
            processed_path, output_dir=output_dir, filename=model_name,
            framework=framework, docker=docker, flat_files=flat_files,
            vsam=vsam, graphql=graphql, kafka=kafka, telemetry=telemetry,
            semantic=semantic, on_progress=_on_progress,
        )

        # Compile the native binary
        console.print(f"  [dim]Compiling native GnuCOBOL binary...[/dim]")
        runtime_dir = os.path.join(output_dir, "runtime")
        compile_res = subprocess.run(
            ["bash", "compile.sh", f"{model_name}.cbl"],
            cwd=runtime_dir, capture_output=True, text=True,
        )

        compiled_ok = compile_res.returncode == 0
        if not compiled_ok:
            console.print(f"  [yellow]Native compilation skipped or failed.[/yellow]")
            if shutil.which("cobc") is None:
                console.print(f"  [dim]GnuCOBOL (cobc) is not installed. "
                              f"The API will still work but the /{{endpoint}} routes will return 503 "
                              f"until you compile the binary.[/dim]")
                console.print(f"  [dim]Install: brew install gnucobol (macOS) or "
                              f"apt install gnucobol (Linux)[/dim]")
            else:
                console.print(f"  [dim]{compile_res.stderr.strip()}[/dim]")

        # Clean up preprocessor temp file
        if os.path.exists(processed_path):
            os.remove(processed_path)

        # --- Success panel ---
        console.print()

        features_str = ", ".join(summary["features"]) if summary["features"] else "none"
        status_str = "[green]compiled[/green]" if compiled_ok else "[yellow]not compiled[/yellow]"

        detail_lines = [
            f"[bold]Program ID:[/bold]    {summary['program_id']}",
            f"[bold]Endpoints:[/bold]     {summary['endpoints']} procedure route(s)",
            f"[bold]Models:[/bold]        {summary['models']} Pydantic model(s)",
            f"[bold]File Descs:[/bold]    {summary['file_descriptions']} FD record(s)",
            f"[bold]Features:[/bold]      {features_str}",
            f"[bold]Binary:[/bold]        {status_str}",
            f"[bold]Output:[/bold]        {output_dir}",
        ]

        panel = Panel(
            "\n".join(detail_lines),
            title="[bold green]Model Loaded Successfully[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
        console.print(panel)

        console.print(f"  [bold]Next step:[/bold] Run [bold cyan]cobol-wrap serve {model_name}[/bold cyan] "
                       f"to start the API server.\n")

    except FileNotFoundError as e:
        _error(str(e))
        raise typer.Exit(code=1)
    except ValueError as e:
        _error(str(e))
        raise typer.Exit(code=1)
    except Exception as e:
        _error(
            f"Failed to load model: {e}",
            hint="Check that the COBOL source is valid and all dependencies are installed.",
            suggestion="cobol-wrap load <file> --verbose",
        )
        console.print(f"  [dim]{type(e).__name__}: {e}[/dim]\n")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# SERVE
# ---------------------------------------------------------------------------

@app.command()
def serve(
    name: str = typer.Argument(..., help="Name of the model to serve"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (use 0.0.0.0 for external access)"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to serve on"),
    reload: bool = typer.Option(False, "--reload", help="Enable hot-reload on source change"),
):
    """Start the REST API server for a loaded COBOL model.

    Launches a FastAPI/Uvicorn server with the generated routes and OpenAPI docs.
    """
    model_dir = _get_model_dir(name)

    if not _model_exists(name):
        _error(
            f"Model '{name}' not found.",
            hint="Make sure you've loaded the model first.",
            suggestion="cobol-wrap list",
        )
        raise typer.Exit(code=1)

    server_py = os.path.join(model_dir, "server.py")
    if not os.path.exists(server_py):
        _error(
            f"Model '{name}' is missing server.py — it may be corrupted.",
            suggestion=f"cobol-wrap load <source.cbl> --name {name}",
        )
        raise typer.Exit(code=1)

    # Show available endpoints
    paths = _read_openapi_paths(model_dir)
    compiled = _is_compiled(model_dir, name)

    console.print()
    console.print(f"  [bold green]Serving[/bold green] model [bold]'{name}'[/bold] "
                  f"on [bold cyan]http://{host}:{port}[/bold cyan]")
    console.print()

    if paths:
        console.print("  [bold]Available endpoints:[/bold]")
        for path in paths:
            console.print(f"    [cyan]POST[/cyan] {path}")
        console.print()

    console.print(f"  [bold]API docs:[/bold]   [link=http://{host}:{port}/docs]http://{host}:{port}/docs[/link]")
    console.print(f"  [bold]OpenAPI:[/bold]    http://{host}:{port}/openapi.json")
    console.print(f"  [bold]Health:[/bold]     http://{host}:{port}/health")

    if not compiled:
        console.print()
        console.print(f"  [yellow]Note:[/yellow] Native binary not compiled. "
                      f"Procedure routes will return HTTP 503.")
        console.print(f"  [dim]Run: cd {model_dir}/runtime && bash compile.sh {name}.cbl[/dim]")

    console.print()
    console.print("  Press [bold]Ctrl+C[/bold] to stop.\n")

    cmd = ["python", "-m", "uvicorn", "server:app", "--host", host, "--port", str(port)]
    if reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd, cwd=model_dir)
    except KeyboardInterrupt:
        console.print("\n  [yellow]Server stopped.[/yellow] Goodbye!\n")


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@app.command("list")
def list_models():
    """List all loaded COBOL models in the local registry.

    Shows each model's name, size, endpoint count, compilation status,
    and last-modified date.
    """
    if not os.path.exists(MODELS_DIR):
        _print_empty_registry()
        return

    models = [d for d in os.listdir(MODELS_DIR) if os.path.isdir(os.path.join(MODELS_DIR, d))]

    if not models:
        _print_empty_registry()
        return

    table = Table(
        title="cobol-wrap Models",
        box=box.ROUNDED,
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("NAME", style="bold cyan", no_wrap=True)
    table.add_column("SIZE", style="magenta", justify="right")
    table.add_column("ENDPOINTS", style="white", justify="center")
    table.add_column("STATUS", justify="center")
    table.add_column("MODIFIED", style="dim")

    for model in sorted(models):
        model_path = os.path.join(MODELS_DIR, model)
        size_kb = f"{_dir_size_kb(model_path)} KB"
        mtime = os.path.getmtime(model_path)
        mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')

        paths = _read_openapi_paths(model_path)
        endpoint_count = str(len(paths)) if paths else "0"

        compiled = _is_compiled(model_path, model)
        status = "[green]compiled[/green]" if compiled else "[yellow]not compiled[/yellow]"

        table.add_row(model, size_kb, endpoint_count, status, mtime_str)

    console.print()
    console.print(table)
    console.print()


def _print_empty_registry():
    console.print()
    console.print(Panel(
        "[dim]No models loaded yet.[/dim]\n\n"
        "Get started by loading a COBOL program:\n"
        "  [bold cyan]cobol-wrap load ./path/to/program.cbl[/bold cyan]",
        title="[bold]cobol-wrap Registry[/bold]",
        border_style="dim",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print()


# ---------------------------------------------------------------------------
# INSPECT
# ---------------------------------------------------------------------------

@app.command()
def inspect(
    name: str = typer.Argument(..., help="Name of the model to inspect"),
):
    """Show detailed information about a loaded model.

    Displays the program ID, endpoints, models, features, compilation status,
    and file sizes.
    """
    model_dir = _get_model_dir(name)

    if not _model_exists(name):
        _error(
            f"Model '{name}' not found.",
            suggestion="cobol-wrap list",
        )
        raise typer.Exit(code=1)

    spec = _read_openapi_spec(model_dir)
    paths = list(spec.get("paths", {}).keys())
    schemas = list(spec.get("components", {}).get("schemas", {}).keys())
    compiled = _is_compiled(model_dir, name)
    size_kb = _dir_size_kb(model_dir)
    mtime = os.path.getmtime(model_dir)
    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

    info = spec.get("info", {})
    program_id = info.get("title", name)

    # Detect enabled features
    features = []
    if os.path.exists(os.path.join(model_dir, "Dockerfile")):
        features.append("docker")
    if os.path.exists(os.path.join(model_dir, "routes", "flatfiles.py")):
        features.append("flat-files")
    if os.path.exists(os.path.join(model_dir, "routes", "graphql_api.py")):
        features.append("graphql")
    if os.path.exists(os.path.join(model_dir, "routes", "kafka_consumers.py")):
        features.append("kafka")

    status_str = "[green]compiled[/green]" if compiled else "[yellow]not compiled[/yellow]"
    features_str = ", ".join(features) if features else "[dim]none[/dim]"

    detail_lines = [
        f"[bold]Program ID:[/bold]    {program_id}",
        f"[bold]Binary:[/bold]        {status_str}",
        f"[bold]Features:[/bold]      {features_str}",
        f"[bold]Total size:[/bold]    {size_kb} KB",
        f"[bold]Last modified:[/bold] {mtime_str}",
        f"[bold]Location:[/bold]      {model_dir}",
    ]

    if paths:
        detail_lines.append("")
        detail_lines.append("[bold]Endpoints:[/bold]")
        for path in paths:
            methods = spec.get("paths", {}).get(path, {})
            for method, details in methods.items():
                summary = details.get("summary", "")
                detail_lines.append(f"  [cyan]{method.upper():6s}[/cyan] {path}  [dim]{summary}[/dim]")

    if schemas:
        detail_lines.append("")
        detail_lines.append(f"[bold]Schemas:[/bold]     {', '.join(schemas)}")

    console.print()
    console.print(Panel(
        "\n".join(detail_lines),
        title=f"[bold cyan]{name}[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print()


# ---------------------------------------------------------------------------
# REMOVE
# ---------------------------------------------------------------------------

@app.command("rm")
def remove(
    name: str = typer.Argument(..., help="Name of the model to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Remove a loaded model from the local registry.

    Deletes the model directory and all generated files.
    """
    if not _model_exists(name):
        _error(
            f"Model '{name}' not found.",
            hint="Check the name with 'cobol-wrap list'.",
            suggestion="cobol-wrap list",
        )
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(f"  Remove model '{name}' and all generated files?")
        if not confirm:
            console.print("  [dim]Cancelled.[/dim]\n")
            raise typer.Exit()

    shutil.rmtree(_get_model_dir(name))
    console.print(f"\n  [bold green]Removed[/bold green] model '{name}' from the registry.\n")


# ---------------------------------------------------------------------------
# PRINT
# ---------------------------------------------------------------------------

print_app = typer.Typer(help="Print generated artifacts and specifications.")
app.add_typer(print_app, name="print")


@print_app.command("api")
def print_api(
    name: str = typer.Argument(..., help="Name of the model"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON instead of YAML"),
):
    """Print the OpenAPI specification for a loaded model.

    Outputs the openapi.yaml spec to stdout. Use --json for JSON format.
    """
    model_dir = _get_model_dir(name)

    if not _model_exists(name):
        _error(
            f"Model '{name}' not found.",
            suggestion="cobol-wrap list",
        )
        raise typer.Exit(code=1)

    openapi_path = os.path.join(model_dir, "openapi.yaml")
    if not os.path.exists(openapi_path):
        _error(
            f"No OpenAPI spec found for model '{name}'.",
            hint="The model may need to be re-loaded.",
            suggestion=f"cobol-wrap load <source.cbl> --name {name}",
        )
        raise typer.Exit(code=1)

    if json_output:
        import json
        spec = _read_openapi_spec(model_dir)
        console.print(json.dumps(spec, indent=2))
    else:
        with open(openapi_path, "r") as f:
            console.print(f.read())


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@app.command()
def ui(port: int = typer.Option(3000, "--port", "-p", help="Port for the dashboard")):
    """Launch the interactive web dashboard.

    Opens a local web UI for browsing and managing loaded COBOL models.
    """
    console.print()
    console.print(f"  [bold cyan]Starting cobol-wrap Dashboard[/bold cyan] "
                  f"on [bold]http://localhost:{port}[/bold]")
    console.print(f"  Press [bold]Ctrl+C[/bold] to stop.\n")
    try:
        subprocess.run([
            "python", "-m", "uvicorn",
            "cobol_wrap.dashboard.app:app",
            "--port", str(port),
        ])
    except KeyboardInterrupt:
        console.print("\n  [yellow]Dashboard stopped.[/yellow] Goodbye!\n")
    except FileNotFoundError:
        _error(
            "Could not start the dashboard server.",
            hint="Make sure uvicorn is installed.",
            suggestion="pip install cobol-wrap[serve]",
        )


if __name__ == "__main__":
    app()
