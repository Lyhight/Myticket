from pathlib import Path

from app.operations.config_validation import validate_project_config


def test_repository_configuration_is_consistent() -> None:
    project_root = Path(__file__).resolve().parents[3]

    assert validate_project_config(project_root) == []
