import pytest
from typer.testing import CliRunner
from cobol_wrap.cli import app
import cobol_wrap.cli as cli
import os

runner = CliRunner()

@pytest.fixture
def mock_models_dir(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(cli, "MODELS_DIR", str(models_dir))
    return models_dir

def test_cli_load_and_list(mock_models_dir, tmp_path):
    cbl = tmp_path / "mock.cbl"
    cbl.write_text("IDENTIFICATION DIVISION.\nPROGRAM-ID. MOCK.\n")
    
    # Test load
    result = runner.invoke(app, ["load", str(cbl), "--name", "testmodel"])
    assert result.exit_code == 0
    assert "Success" in result.stdout
    assert "testmodel" in result.stdout
    
    model_path = os.path.join(mock_models_dir, "testmodel")
    assert os.path.exists(os.path.join(model_path, "server.py"))
    assert os.path.exists(os.path.join(model_path, "models.py"))
    assert os.path.exists(os.path.join(model_path, "openapi.yaml"))
    
    # Test list
    result_list = runner.invoke(app, ["list"])
    assert result_list.exit_code == 0
    assert "testmodel" in result_list.stdout

def test_cli_print_api(mock_models_dir, tmp_path):
    cbl = tmp_path / "mock.cbl"
    cbl.write_text("IDENTIFICATION DIVISION.\nPROGRAM-ID. MOCK.\n")
    
    # Load first
    runner.invoke(app, ["load", str(cbl), "--name", "testmodel"])
    
    # Test print api
    result_print = runner.invoke(app, ["print", "api", "testmodel"])
    assert result_print.exit_code == 0
    assert "openapi: 3.1.0" in result_print.stdout
    assert "testmodel" in result_print.stdout
